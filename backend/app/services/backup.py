"""Backup and restore of the hub (Administration → Backup).

An archive is a ZIP file with

- ``manifest.json``: format, hub version, Alembic revision, creation time, database dialect, row counts,
- ``db/<table>.jsonl``: every table of the hub as JSON lines (avatars as base64). Settings that hold
  secrets stay Fernet-encrypted exactly as stored; nothing is decrypted for the backup,
- ``files/secret_key`` and ``files/vapid.json`` (optional): the keys from the data folder. Without the
  secret key the stored plugin credentials cannot be decrypted after a restore on a new machine.
  An archive with keys must be kept as carefully as the data volume itself.

Plugins and themes are database rows (``installed_plugins``, ``themes``) and travel with it. The source
code of installed plugins is not part of the archive; the hub loads what it finds again and logs plugins
whose files are missing.

The dump is logical, so it works the same for SQLite and PostgreSQL. SQLite is first copied with the
online backup API (never a plain file copy of a live database) and the copy is dumped; PostgreSQL is read
in one ``REPEATABLE READ`` transaction. A restore needs the same Alembic revision as the running hub and
refuses archives of a newer hub version.

Everything here is blocking; routers call it from worker threads.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import zipfile
from datetime import date, datetime, time as dtime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import Date, DateTime, LargeBinary, Numeric, Time, create_engine, delete, inspect as sa_inspect, select, text
from sqlalchemy.engine import Connection, Engine

from app import __version__
from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger("service.backup")

FORMAT = 1
MANIFEST = "manifest.json"
KEY_FILES = ("secret_key", "vapid.json")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.zip$")
_ENTRY_RE = re.compile(r"^(manifest\.json|db/[A-Za-z0-9_]{1,63}\.jsonl|files/(secret_key|vapid\.json))$")
MAX_ENTRY_BYTES = 4 * 1024 ** 3
MAX_TOTAL_BYTES = 8 * 1024 ** 3
MAX_MANIFEST_BYTES = 1024 * 1024
BATCH = 500

KIND_PREFIX = {"auto": "familienhub-auto-", "manual": "familienhub-backup-",
               "safety": "familienhub-prerestore-", "uploaded": "familienhub-uploaded-"}
KEEP_SAFETY = 3

_lock = threading.Lock()  # one backup or restore at a time


class BackupError(Exception):
    """A backup or restore that cannot proceed. ``code`` is stable (the app translates it)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# --- Paths and status ---

def backups_dir() -> Path:
    return Path(settings.data_dir) / "backups"


def _ensure_dir() -> Path:
    base = backups_dir()
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BackupError("dir_not_writable", "The data folder is not writable. Mount a volume at /app/data") from exc
    if not os.access(base, os.W_OK):
        raise BackupError("dir_not_writable", "The data folder is not writable. Mount a volume at /app/data")
    return base


def _status_file() -> Path:
    return backups_dir() / "status.json"


def read_status() -> Dict[str, Any]:
    try:
        data = json.loads(_status_file().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_status(**changes: Any) -> None:
    try:
        data = read_status()
        data.update(changes)
        base = _ensure_dir()
        tmp = base / ".status.tmp"
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, _status_file())
    except (OSError, BackupError) as exc:
        logger.warning("backup status not saved: %s", type(exc).__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def truthy(value: Any) -> bool:
    return value if isinstance(value, bool) else str(value).strip().lower() in ("1", "true", "yes", "on")


def auto_enabled() -> bool:
    return truthy(settings.backup_auto)


def keep_count() -> int:
    try:
        return max(1, min(60, int(settings.backup_keep)))
    except (TypeError, ValueError):
        return 7


# --- Versions ---

_VER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")


def parse_version(value: Optional[str]) -> Optional[Tuple]:
    """Sortable key of a semantic version ("1.2.3", "v1.2.3-beta.1"); None for "dev" and other texts."""
    m = _VER.match((value or "").strip())
    if not m:
        return None
    pre = m.group(4)
    ids: Tuple = ()
    if pre:
        ids = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split("."))
    # A release sorts after its pre-releases
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), 0 if pre else 1, ids)


def is_prerelease(value: Optional[str]) -> bool:
    key = parse_version(value)
    return bool(key and key[3] == 0)


# --- Database access ---

def _tables():
    from app import models  # noqa: F401  (registers every table)
    from app.core.database import Base

    return list(Base.metadata.sorted_tables)


def current_revision(engine: Optional[Engine] = None) -> Optional[str]:
    from alembic.runtime.migration import MigrationContext

    from app.core.database import engine as default_engine

    with (engine or default_engine).connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def known_revisions() -> set:
    from alembic.script import ScriptDirectory

    from app.core.database import _alembic_config

    script = ScriptDirectory.from_config(_alembic_config())
    return {r.revision for r in script.walk_revisions()}


def _jsonable(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(value)).decode("ascii")
    if isinstance(value, (datetime, date, dtime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _from_json(column, value: Any) -> Any:
    if value is None:
        return None
    t = column.type
    try:
        if isinstance(t, LargeBinary):
            return base64.b64decode(value)
        if isinstance(t, DateTime):
            return datetime.fromisoformat(value)
        if isinstance(t, Date):
            return date.fromisoformat(value)
        if isinstance(t, Time):
            return dtime.fromisoformat(value)
        if isinstance(t, Numeric) and getattr(t, "asdecimal", False):
            return Decimal(value)
    except (TypeError, ValueError) as exc:
        raise BackupError("corrupt", f"Column {column.table.name}.{column.name} holds an invalid value") from exc
    return value


def _snapshot_sqlite(dest: Path) -> Engine:
    """Consistent copy of a live SQLite database with the online backup API; returns an engine on the copy."""
    from app.core.database import engine

    raw = engine.raw_connection()
    try:
        target = sqlite3.connect(str(dest))
        try:
            raw.driver_connection.backup(target)
        finally:
            target.close()
    finally:
        raw.close()
    return create_engine(f"sqlite:///{dest}")


def _dump_tables(conn: Connection, zf: zipfile.ZipFile) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    existing = set(sa_inspect(conn).get_table_names())
    for table in _tables():
        if table.name not in existing:
            continue
        n = 0
        with zf.open(f"db/{table.name}.jsonl", "w", force_zip64=True) as out:
            result = conn.execution_options(stream_results=True).execute(select(table))
            for row in result:
                line = {c.name: _jsonable(row._mapping[c]) for c in table.columns}
                out.write(json.dumps(line, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n")
                n += 1
        counts[table.name] = n
    return counts


def _ordered_names(kind: str, ts: datetime) -> str:
    return f"{KIND_PREFIX[kind]}{ts.strftime('%Y%m%d-%H%M%S')}.zip"


def create_archive(dest: Path, *, include_keys: bool = True) -> Dict[str, Any]:
    """Writes a backup archive to ``dest`` (atomically: temp file, then rename). Returns the manifest."""
    from app.core.database import engine

    dialect = engine.dialect.name
    tmpdir = Path(tempfile.mkdtemp(prefix="fh-snap-", dir=str(dest.parent)))
    snap_engine: Optional[Engine] = None
    part = dest.with_name(dest.name + ".part")
    try:
        if dialect == "sqlite":
            snap_engine = _snapshot_sqlite(tmpdir / "snapshot.db")
            conn = snap_engine.connect()
        else:
            conn = engine.connect().execution_options(isolation_level="REPEATABLE READ")
        try:
            revision = current_revision(snap_engine or engine)
            with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as zf:
                counts = _dump_tables(conn, zf)
                files: List[str] = []
                if include_keys:
                    for name in KEY_FILES:
                        src = Path(settings.data_dir) / name
                        if src.is_file():
                            zf.write(src, f"files/{name}")
                            files.append(name)
                manifest = {
                    "format": FORMAT,
                    "hub_version": __version__,
                    "alembic_revision": revision,
                    "created_at": _now().isoformat(),
                    "dialect": dialect,
                    "tables": counts,
                    "files": files,
                    "includes_keys": bool(files),
                }
                zf.writestr(MANIFEST, json.dumps(manifest, indent=2))
        finally:
            conn.close()
        os.chmod(part, 0o600)
        os.replace(part, dest)
        return manifest
    finally:
        if snap_engine is not None:
            snap_engine.dispose()
        shutil.rmtree(tmpdir, ignore_errors=True)
        try:
            part.unlink()
        except OSError:
            pass


def create_backup(kind: str = "manual", *, include_keys: bool = True) -> Dict[str, Any]:
    """Stores a backup in the data folder. Never raises: returns ``{"ok": False, ...}`` on failure."""
    if not _lock.acquire(blocking=False):
        return {"ok": False, "code": "busy", "message": "Another backup or restore is running"}
    try:
        base = _ensure_dir()
        name = _ordered_names(kind, _now())
        manifest = create_archive(base / name, include_keys=include_keys)
        size = (base / name).stat().st_size
        _write_status(last_at=manifest["created_at"], last_kind=kind, last_ok=True, last_name=name,
                      last_size=size, last_error=None)
        if kind == "auto":
            _write_status(last_auto_date=_now().astimezone(_local_tz()).date().isoformat())
        _prune()
        logger.info("audit: backup %s created (%s, %d bytes)", name, kind, size)
        return {"ok": True, "name": name, "size": size, "created_at": manifest["created_at"], "kind": kind}
    except BackupError as exc:
        _fail(kind, exc.code, exc.message)
        return {"ok": False, "code": exc.code, "message": exc.message}
    except Exception as exc:  # noqa: BLE001  - a failed backup must never take the hub down
        _fail(kind, "failed", type(exc).__name__)
        return {"ok": False, "code": "failed", "message": "The backup failed. See the hub log"}
    finally:
        _lock.release()


def _fail(kind: str, code: str, message: str) -> None:
    logger.warning("audit: backup (%s) failed: %s %s", kind, code, message)
    _write_status(last_ok=False, last_error=code, last_error_at=_now().isoformat())


def _local_tz():
    from zoneinfo import ZoneInfo

    try:
        return ZoneInfo(settings.timezone)
    except Exception:  # noqa: BLE001
        return timezone.utc


# --- Stored backups ---

def safe_path(name: str) -> Path:
    if not NAME_RE.match(name or ""):
        raise BackupError("bad_name", "Invalid backup name")
    path = backups_dir() / name
    if not path.is_file() or path.is_symlink():
        raise BackupError("not_found", "Backup not found")
    return path


def kind_of(name: str) -> str:
    for kind, prefix in KIND_PREFIX.items():
        if name.startswith(prefix):
            return kind
    return "other"


def _read_manifest_quiet(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return read_manifest(path)
    except BackupError:
        return None


def list_backups() -> List[Dict[str, Any]]:
    out = []
    try:
        entries = [p for p in backups_dir().iterdir() if p.is_file() and NAME_RE.match(p.name)]
    except OSError:
        return []
    for p in entries:
        try:
            st = p.stat()
        except OSError:
            continue
        m = _read_manifest_quiet(p)
        out.append({
            "name": p.name, "size": st.st_size, "kind": kind_of(p.name),
            "created_at": (m or {}).get("created_at") or datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
            "hub_version": (m or {}).get("hub_version"), "includes_keys": bool((m or {}).get("includes_keys")),
            "valid": m is not None,
        })
    out.sort(key=lambda b: b["created_at"] or "", reverse=True)
    return out


def delete_backup(name: str) -> None:
    safe_path(name).unlink()
    logger.info("audit: backup %s deleted", name)


def _prune() -> None:
    items = list_backups()
    for kind, keep in (("auto", keep_count()), ("safety", KEEP_SAFETY)):
        for b in [i for i in items if i["kind"] == kind][keep:]:
            try:
                (backups_dir() / b["name"]).unlink()
            except OSError:
                pass


# --- Validation ---

def read_manifest(path: Path) -> Dict[str, Any]:
    """Opens an archive and checks its structure (member names, sizes, manifest). Raises BackupError."""
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise BackupError("not_a_backup", "This is not a Familienhub backup file") from exc
    with zf:
        infos = zf.infolist()
        total = 0
        for info in infos:
            if not _ENTRY_RE.match(info.filename) or info.is_dir():
                raise BackupError("unsafe", "The archive contains unexpected files and was not used")
            if info.file_size > MAX_ENTRY_BYTES:
                raise BackupError("unsafe", "The archive is unreasonably large and was not used")
            total += info.file_size
        if total > MAX_TOTAL_BYTES or len({i.filename for i in infos}) != len(infos):
            raise BackupError("unsafe", "The archive is unreasonably large and was not used")
        try:
            info = zf.getinfo(MANIFEST)
        except KeyError as exc:
            raise BackupError("not_a_backup", "This is not a Familienhub backup file") from exc
        if info.file_size > MAX_MANIFEST_BYTES:
            raise BackupError("not_a_backup", "This is not a Familienhub backup file")
        try:
            manifest = json.loads(zf.read(info))
        except (ValueError, zipfile.BadZipFile) as exc:
            raise BackupError("not_a_backup", "This is not a Familienhub backup file") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("format"), int) \
            or not isinstance(manifest.get("tables"), dict) or not isinstance(manifest.get("hub_version"), str):
        raise BackupError("not_a_backup", "This is not a Familienhub backup file")
    return manifest


def check_compatible(manifest: Dict[str, Any]) -> None:
    """Version check: no restore of a newer backup into an older hub, and the schema must match."""
    if manifest["format"] > FORMAT:
        raise BackupError("newer_version", "This backup was made by a newer Familienhub. Update the hub first")
    theirs, ours = parse_version(manifest["hub_version"]), parse_version(__version__)
    if theirs and ours and theirs > ours:
        raise BackupError("newer_version", f"This backup was made by Familienhub {manifest['hub_version']}, "
                          f"newer than this hub ({__version__}). Update the hub first")
    revision = manifest.get("alembic_revision")
    here = current_revision()
    if revision != here:
        if revision in known_revisions():
            raise BackupError("older_schema", f"This backup is from an older database layout (Familienhub "
                              f"{manifest['hub_version']}). Run that version, restore, then update")
        raise BackupError("newer_version", "This backup was made by a newer Familienhub. Update the hub first")


def inspect_backup(name: str) -> Dict[str, Any]:
    """Validation result for the UI: never raises."""
    try:
        path = safe_path(name)
        manifest = read_manifest(path)
        check_compatible(manifest)
        return {"ok": True, "manifest": _public_manifest(manifest)}
    except BackupError as exc:
        return {"ok": False, "code": exc.code, "message": exc.message}


def _public_manifest(m: Dict[str, Any]) -> Dict[str, Any]:
    return {"hub_version": m.get("hub_version"), "created_at": m.get("created_at"), "dialect": m.get("dialect"),
            "includes_keys": bool(m.get("includes_keys")), "rows": sum(v for v in m["tables"].values() if isinstance(v, int))}


# --- Restore ---

def _read_rows(zf: zipfile.ZipFile, table):
    try:
        info = zf.getinfo(f"db/{table.name}.jsonl")
    except KeyError:
        return
    columns = {c.name: c for c in table.columns}
    with zf.open(info) as fh:
        for raw in fh:
            if not raw.strip():
                continue
            try:
                record = json.loads(raw)
            except ValueError as exc:
                raise BackupError("corrupt", f"Table {table.name} in the archive is damaged") from exc
            if not isinstance(record, dict):
                raise BackupError("corrupt", f"Table {table.name} in the archive is damaged")
            yield {k: _from_json(columns[k], v) for k, v in record.items() if k in columns}


def _reset_sequences(conn: Connection) -> None:
    if conn.dialect.name != "postgresql":
        return
    for table in _tables():
        pk = list(table.primary_key.columns)
        if len(pk) == 1 and pk[0].autoincrement is not False and pk[0].type.python_type is int:
            col = pk[0].name
            conn.execute(text(
                f'SELECT setval(pg_get_serial_sequence(:t, :c), COALESCE(MAX("{col}"), 1), MAX("{col}") IS NOT NULL) '
                f'FROM "{table.name}"'), {"t": table.name, "c": col})


def _write_key_file(name: str, data: bytes) -> None:
    target = Path(settings.data_dir) / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.copy2(target, target.with_name(name + ".before-restore"))
    fd, tmp = tempfile.mkstemp(prefix=f".{name}.", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def restore_backup(name: str) -> Dict[str, Any]:
    """Replaces the hub's data with a stored backup. Returns a result dict; never raises."""
    if not _lock.acquire(blocking=False):
        return {"ok": False, "code": "busy", "message": "Another backup or restore is running"}
    try:
        path = safe_path(name)
        manifest = read_manifest(path)
        check_compatible(manifest)
        # Safety net: the state before the restore stays available as a backup of its own
        safety = _ensure_dir() / _ordered_names("safety", _now())
        try:
            create_archive(safety)
        except Exception as exc:  # noqa: BLE001
            logger.warning("audit: restore of %s aborted, safety backup failed: %s", name, type(exc).__name__)
            return {"ok": False, "code": "safety_backup_failed",
                    "message": "The current data could not be backed up first, so nothing was restored"}
        from app.core.database import engine

        with zipfile.ZipFile(path) as zf:
            tables = _tables()
            with engine.begin() as conn:
                for table in reversed(tables):
                    conn.execute(delete(table))
                restored = 0
                for table in tables:
                    batch: List[Dict[str, Any]] = []
                    for row in _read_rows(zf, table):
                        batch.append(row)
                        if len(batch) >= BATCH:
                            conn.execute(table.insert(), batch)
                            restored += len(batch)
                            batch = []
                    if batch:
                        conn.execute(table.insert(), batch)
                        restored += len(batch)
                _reset_sequences(conn)
            warnings: List[str] = []
            for key_file in KEY_FILES:
                member = f"files/{key_file}"
                if member not in zf.namelist():
                    continue
                if key_file == "secret_key" and os.environ.get("SECRET_KEY", "").strip():
                    warnings.append("secret_key_env")  # an explicit SECRET_KEY wins; the file would be ignored
                    continue
                try:
                    _write_key_file(key_file, zf.read(member))
                except OSError:
                    warnings.append(f"{key_file}_not_written")
        _write_status(last_restore_at=_now().isoformat(), last_restore_name=name)
        logger.info("audit: restored backup %s (%d rows, safety copy %s)", name, restored, safety.name)
        return {"ok": True, "rows": restored, "restart_required": True, "safety_backup": safety.name,
                "warnings": warnings}
    except BackupError as exc:
        logger.warning("audit: restore of %s refused: %s", name, exc.code)
        return {"ok": False, "code": exc.code, "message": exc.message}
    except Exception as exc:  # noqa: BLE001
        logger.error("audit: restore of %s failed: %s", name, type(exc).__name__)
        return {"ok": False, "code": "restore_failed",
                "message": "The restore failed and the database was left unchanged. See the hub log"}
    finally:
        _lock.release()


# --- Upload ---

def upload_part_path() -> Path:
    """Where the router streams an upload to before it is checked."""
    return _ensure_dir() / f".upload-{os.urandom(6).hex()}.part"


def finish_upload(part: Path) -> Dict[str, Any]:
    """Checks a streamed upload and, if it is a backup, stores it next to the others."""
    name = _ordered_names("uploaded", _now())
    try:
        os.chmod(part, 0o600)
        read_manifest(part)
        os.replace(part, backups_dir() / name)
    finally:
        try:
            part.unlink()
        except OSError:
            pass
    logger.info("audit: backup file uploaded as %s", name)
    return inspect_backup(name) | {"name": name}


# --- Nightly job ---

AUTO_HOUR = 3
AUTO_MINUTE = 30


def auto_due(now: Optional[datetime] = None) -> bool:
    """True once per local day, from 03:30 on, when nightly backups are switched on."""
    if not auto_enabled():
        return False
    local = (now or _now()).astimezone(_local_tz())
    if (local.hour, local.minute) < (AUTO_HOUR, AUTO_MINUTE):
        return False
    return read_status().get("last_auto_date") != local.date().isoformat()


def run_auto_if_due() -> Optional[Dict[str, Any]]:
    if not auto_due():
        return None
    result = create_backup("auto")
    if not result.get("ok") and result.get("code") != "busy":
        # Do not retry every minute: mark today as tried
        _write_status(last_auto_date=_now().astimezone(_local_tz()).date().isoformat())
    return result


def summary() -> Dict[str, Any]:
    """What the overview shows: when the last backup was made."""
    s = read_status()
    return {"last_at": s.get("last_at"), "last_ok": s.get("last_ok"), "auto": auto_enabled()}
