"""Installs, loads, updates and removes plugins that come from GitHub.

Flow (``docs/plugins.md``): the admin pastes a link, ``inspect_plugin`` resolves it to one commit and shows
the manifest. ``install_plugin`` re-reads the manifest at that commit, downloads exactly that commit's
tarball, extracts it safely into ``<DATA_DIR>/plugins/src``, installs the Python package with
``pip install --target <DATA_DIR>/plugins/site/<id>``, stores the settings through the config store
(secrets encrypted) and hot-loads the plugin into the running app. At start-up ``load_installed`` loads
every recorded plugin again; one that fails is logged and skipped.

Installed plugins run inside the hub process with full access. The checks here (admin only, pinned
commit, allow-listed hosts, safe extraction, namespaced and authenticated routes, settings namespace)
limit accidents and sloppy plugins, they do not sandbox code. The admin sees that warning before every install.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import os
import secrets
import shlex
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session

from app import __version__
from app.config import settings
from app.core import i18n
from app.core.logging_config import get_logger
from app.models.installed_plugin import InstalledPlugin
from app.plugins import archive, github
from app.plugins.base import CAPABILITIES, as_plugin, get_setting
from app.plugins.manifest import (MANIFEST_FILE, check_value, english, form_spec, german, hub_version_ok, localized,
                                  parse_manifest, settings_for, validate_manifest)
from app.plugins.registry import plugin_registry
from app.services import config_store

logger = get_logger("plugins.installer")
# Install and remove events are logged as warnings on purpose: the in-app protocol (Administration → Log)
# keeps warnings and errors, and a change to the code the hub runs belongs in it.
audit = get_logger("plugins.audit")

PIP_TIMEOUT = 300  # seconds
PIP_LOG_TAIL = 400  # characters of pip's output shown to the admin on failure


class InstallError(ValueError):
    """The plugin cannot be installed or loaded; the message is German and meant for the admin."""


@dataclass
class _Loaded:
    site_dir: Path
    routes: List[Any] = field(default_factory=list)


_loaded: Dict[str, _Loaded] = {}
_errors: Dict[str, str] = {}
_lock = asyncio.Lock()  # one install, update or removal at a time


# --- Paths and environment ---

def plugins_dir() -> Path:
    return Path(settings.data_dir) / "plugins"


def site_dir(plugin_id: str) -> Path:
    return plugins_dir() / "site" / plugin_id


def prepare_dirs() -> Path:
    base = plugins_dir()
    try:
        for sub in ("src", "site", "tmp"):
            (base / sub).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise InstallError("Der Datenordner ist nicht beschreibbar. Bitte ein Volume unter /app/data einbinden") from exc
    if not os.access(base, os.W_OK):
        raise InstallError("Der Datenordner ist nicht beschreibbar. Bitte ein Volume unter /app/data einbinden")
    return base


def data_dir_persistent() -> Optional[bool]:
    """Is the data folder on its own mount (a volume)? None if that cannot be told."""
    try:
        text = Path("/proc/self/mountinfo").read_text()
        target = str(Path(settings.data_dir).resolve())
    except OSError:
        return None
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        mount = parts[4]
        if mount != "/" and (target == mount or target.startswith(mount.rstrip("/") + "/")):
            return True
    return False


def short_sha(sha: str) -> str:
    return (sha or "")[:7]


def source_url(ref: github.RepoRef) -> str:
    """Normalised link the admin pasted: the repository, plus branch and folder if given (kept for updates)."""
    return ref.url + "/tree/" + "/".join(ref.rest) if ref.rest else ref.url


# --- Settings of the installing form ---

def _stored(key: str) -> str:
    return str(get_setting(key) or "")


def check_settings(manifest: Dict[str, Any], values: Dict[str, Any]) -> Dict[str, str]:
    """Validated values to store. Secrets left empty stay as they are; missing required values are an error."""
    specs = {s["key"]: s for s in manifest["settings"]}
    unknown = sorted(set(values or {}) - set(specs))
    if unknown:
        raise ValueError(f"Unbekannte Einstellung: {', '.join(unknown)}")
    out: Dict[str, str] = {}
    missing: List[str] = []
    for key, spec in specs.items():
        raw = (values or {}).get(key)
        if isinstance(raw, bool):
            raw = "true" if raw else "false"
        elif isinstance(raw, (int, float)):
            raw = str(raw)
        elif raw is None:
            raw = ""
        elif not isinstance(raw, str):
            raise ValueError(f"Wert von {key} ist ungültig")
        raw = raw.strip()
        if raw:
            out[key] = check_value(spec["type"], raw, key)
            continue
        if spec["secret"]:
            if spec["required"] and not _stored(key):
                missing.append(key)
            continue
        if _stored(key):
            continue
        if spec["default"] is not None:
            out[key] = spec["default"]
        elif spec["type"] == "bool":
            out[key] = "false"
        elif spec["required"]:
            missing.append(key)
    if missing:
        raise ValueError(f"Pflichtfelder fehlen: {', '.join(missing)}")
    return out


# --- Checks before anything is downloaded ---

def check_installable(manifest: Dict[str, Any], repo_url: str, db: Session) -> Optional[InstalledPlugin]:
    """Raises ``InstallError`` if this manifest may not be installed here; returns the current record (update)."""
    plugin_id = manifest["id"]
    if manifest["min_hub_version"] and not hub_version_ok(manifest["min_hub_version"], __version__):
        raise InstallError(f"Das Plugin braucht Familienhub {manifest['min_hub_version']} oder neuer (dieser Hub: {__version__})")
    row = db.get(InstalledPlugin, plugin_id)
    if row is None and plugin_registry.get(plugin_id) is not None:
        raise InstallError(f"Die Plugin-ID „{plugin_id}“ ist schon vergeben")
    if row is not None and github.parse_repo_url(row.repo_url).url.lower() != github.parse_repo_url(repo_url).url.lower():
        raise InstallError(f"Das Plugin „{plugin_id}“ ist schon aus einem anderen Repository installiert")
    keys = {s["key"].upper() for s in manifest["settings"]}
    taken = {s.key.upper() for p in plugin_registry.all() if p.id != plugin_id for s in p.settings}
    taken |= {s.key.upper() for s in config_store._core_settings()}  # noqa: SLF001
    clash = sorted(keys & taken)
    if clash:
        raise InstallError(f"Einstellungen kollidieren mit anderen Plugins oder dem Hub: {', '.join(clash)}")
    return row


async def read_manifest(url: str) -> tuple:
    """(RepoRef, folder, sha, manifest) for a pasted link."""
    ref = github.parse_repo_url(url)
    sha, folder = await github.resolve_sha(ref)
    manifest = parse_manifest(await github.fetch_manifest_bytes(ref, sha, folder, MANIFEST_FILE))
    return ref, folder, sha, manifest


async def inspect_plugin(url: str, lang: str, db: Session) -> Dict[str, Any]:
    ref, folder, sha, manifest = await read_manifest(url)
    link = source_url(ref)
    row = check_installable(manifest, link, db)
    warnings: List[str] = []
    if data_dir_persistent() is False:
        warnings.append("Der Datenordner scheint kein eigenes Volume zu sein. Beim Neu-Erstellen des Containers gehen "
                        "installierte Plugins verloren")
    if not manifest["hosts"]:
        warnings.append("Das Plugin gibt keine Server an, mit denen es sich verbindet")
    form = form_spec(manifest, lang)
    for item in form:
        item["is_set"] = bool(_stored(item["key"]))
        item["value"] = "" if item["secret"] else (_stored(item["key"]) or item["default"] or "")
    installed = None
    if row is not None:
        installed = {"version": row.version, "sha": row.sha, "short_sha": short_sha(row.sha), "same_sha": row.sha == sha}
    return {
        "url": link,
        "repo": {"url": ref.url, "owner": ref.owner, "repo": ref.repo, "folder": folder},
        "sha": sha,
        "short_sha": short_sha(sha),
        "manifest": summary(manifest, lang),
        "settings": form,
        "installed": installed,
        "warnings": [i18n.translate(w, lang) for w in warnings],
        "install_enabled": settings.plugin_install_enabled,
    }


def summary(manifest: Dict[str, Any], lang: str) -> Dict[str, Any]:
    return {
        "id": manifest["id"],
        "name": localized(manifest["name"], lang),
        "version": manifest["version"],
        "description": localized(manifest["description"], lang),
        "author": manifest["author"],
        "homepage": manifest["homepage"],
        "license": manifest["license"],
        "min_hub_version": manifest["min_hub_version"],
        "hosts": manifest["hosts"],
        "capabilities": [{"id": c, "label": i18n.translate(CAPABILITIES[c], lang)} for c in manifest["capabilities"]],
    }


# --- pip ---

def pip_command(package_dir: Path, target: Path) -> List[str]:
    """The pip call. Tests replace this (offline, no build isolation)."""
    extra = shlex.split(settings.plugin_pip_args or "")
    return [sys.executable, "-m", "pip", "install", "--no-cache-dir", "--disable-pip-version-check", "--no-input",
            "--target", str(target), *extra, str(package_dir)]


_ENV_KEEP = ("PATH", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "HTTP_PROXY", "HTTPS_PROXY",
             "NO_PROXY", "http_proxy", "https_proxy", "no_proxy", "PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "PIP_CERT",
             "PIP_TRUSTED_HOST", "PIP_NO_INDEX", "PIP_FIND_LINKS")


def _build_env(tmp: Path) -> Dict[str, str]:
    """A plugin's build scripts run during pip; they get no hub secrets (SECRET_KEY, DATABASE_URL …)."""
    env = {k: os.environ[k] for k in _ENV_KEEP if k in os.environ}
    env.update({"HOME": str(tmp), "TMPDIR": str(tmp), "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    return env


async def run_pip(package_dir: Path, target: Path, tmp: Path) -> None:
    cmd = pip_command(package_dir, target)
    proc = await asyncio.create_subprocess_exec(  # no shell: the arguments are never interpreted
        *cmd, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        env=_build_env(tmp), cwd=str(tmp))
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), PIP_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise InstallError("Die Installation hat zu lange gedauert (pip, Zeitüberschreitung)") from None
    text = out.decode("utf-8", "replace").strip()
    if proc.returncode != 0:
        logger.warning("pip für %s fehlgeschlagen (Code %s): %s", package_dir.name, proc.returncode, text[-PIP_LOG_TAIL:])
        raise InstallError(f"Die Abhängigkeiten ließen sich nicht installieren (pip): {text[-PIP_LOG_TAIL:] or 'keine Ausgabe'}")
    logger.info("pip für %s: %s", package_dir.name, text[-200:])


# --- Loading into the running app ---

def _under(path: Path, folder: Path) -> bool:
    try:
        return Path(path).resolve().is_relative_to(folder.resolve())
    except (OSError, ValueError):
        return False


def purge_modules(folder: Path) -> bool:
    """Forget every module loaded from ``folder`` and take it off ``sys.path``. True if one was a native extension."""
    native = False
    for name, module in list(sys.modules.items()):
        files = [getattr(module, "__file__", None)] + list(getattr(module, "__path__", []) or [])
        if any(f and _under(Path(f), folder) for f in files):
            native = native or str(getattr(module, "__file__", "") or "").endswith((".so", ".pyd"))
            sys.modules.pop(name, None)
    sys.path[:] = [p for p in sys.path if p != str(folder)]
    importlib.invalidate_caches()
    return native


def _frontend_index(app: FastAPI) -> int:
    """Position of the catch-all frontend mount; plugin routes must sit before it or they are never reached."""
    from starlette.routing import Mount

    for i, route in enumerate(app.router.routes):
        if isinstance(route, Mount) and route.path in ("", "/"):
            return i
    return len(app.router.routes)


def _mount(app: FastAPI, plugin) -> List[Any]:
    """Routes of an installed plugin: only below /api/plugins/<id>/, and always for logged-in users."""
    from app.core.security import get_current_user

    prefix = f"/api/plugins/{plugin.id}"
    routers = plugin.routers()
    for router in routers:
        for route in router.routes:
            path = getattr(route, "path", "")
            if not (path == prefix or path.startswith(prefix + "/")):
                raise InstallError(f"Die Route {path} liegt nicht unter {prefix}/")
    before = len(app.router.routes)
    for router in routers:
        app.include_router(router, dependencies=[Depends(get_current_user)])
    new = app.router.routes[before:]
    del app.router.routes[before:]
    index = _frontend_index(app)
    app.router.routes[index:index] = new
    app.openapi_schema = None
    return list(new)


def load_plugin(app: FastAPI, manifest: Dict[str, Any], folder: Path) -> Any:
    """Import the entry point from ``folder``, check it against the manifest, register it, mount its routes."""
    plugin_id = manifest["id"]
    module_name, _, attr = manifest["entry_point"].partition(":")
    top = module_name.split(".")[0]
    purge_modules(folder)  # leftovers of an earlier attempt
    if top == "app" or top in sys.stdlib_module_names or top in sys.modules or importlib.util.find_spec(top) is not None:
        raise InstallError(f"Der Modulname „{top}“ ist schon belegt. Bitte ein eindeutiges Paket wie fh_plugin_{plugin_id} verwenden")
    sys.path.append(str(folder))
    importlib.invalidate_caches()
    try:
        try:
            module = importlib.import_module(module_name)
            plugin = as_plugin(getattr(module, attr))
        except Exception as exc:  # noqa: BLE001 – a broken plugin must never stop the hub
            raise InstallError(f"Das Plugin lässt sich nicht laden: {type(exc).__name__}: {str(exc)[:200]}") from exc
        if not _under(Path(getattr(module, "__file__", "") or "/nonexistent"), folder):
            raise InstallError("Das Plugin-Modul stammt nicht aus dem installierten Paket")
        if plugin is None:
            raise InstallError("Der Einstiegspunkt liefert kein Plugin")
        if plugin.id != plugin_id:
            raise InstallError(f"Die Plugin-ID im Code („{plugin.id}“) weicht vom Manifest („{plugin_id}“) ab")
        keys = {s["key"] for s in manifest["settings"]}
        undeclared = sorted({s.key for s in plugin.settings} - keys)
        if undeclared:
            raise InstallError(f"Einstellungen fehlen im Manifest: {', '.join(undeclared)}")
        extra_caps = sorted(set(plugin.capabilities) - set(manifest["capabilities"]))
        if extra_caps:
            raise InstallError(f"Fähigkeiten fehlen im Manifest: {', '.join(extra_caps)}")
        # The manifest is the source of truth for what the admin sees and what may be stored
        plugin.name = german(manifest["name"])
        plugin.version = manifest["version"]
        plugin.description = german(manifest["description"])
        plugin.settings = settings_for(manifest)
        plugin.builtin = False
        routes = _mount_checked(app, plugin)
    except BaseException:
        purge_modules(folder)
        raise
    translations = {german(manifest["name"]): english(manifest["name"]),
                    german(manifest["description"]): english(manifest["description"])}
    for s in manifest["settings"]:
        translations[german(s["label"])] = english(s["label"])
        if s["help"]:
            translations[german(s["help"])] = english(s["help"])
    i18n.add_runtime_translations(translations)
    _loaded[plugin_id] = _Loaded(folder, routes)
    _errors.pop(plugin_id, None)
    return plugin


def _mount_checked(app: FastAPI, plugin) -> List[Any]:
    routes = _mount(app, plugin)
    if not plugin_registry.register(plugin):
        ids = {id(r) for r in routes}
        app.router.routes[:] = [r for r in app.router.routes if id(r) not in ids]
        raise InstallError(f"Die Plugin-ID „{plugin.id}“ ist schon vergeben")
    return routes


def unload_plugin(app: FastAPI, plugin_id: str) -> bool:
    """Take a loaded plugin out of the running app. True if native extension modules stay in memory."""
    loaded = _loaded.pop(plugin_id, None)
    plugin_registry.unregister(plugin_id)
    if loaded is None:
        return False
    ids = {id(r) for r in loaded.routes}
    app.router.routes[:] = [r for r in app.router.routes if id(r) not in ids]
    app.openapi_schema = None
    return purge_modules(loaded.site_dir)


def load_installed(app: FastAPI) -> None:
    """At start-up: load every recorded plugin. One that fails is logged and skipped."""
    from app.core.database import SessionLocal

    with SessionLocal() as db:
        rows = db.query(InstalledPlugin).all()
    for row in rows:
        if row.id in _loaded or plugin_registry.get(row.id) is not None:
            continue
        try:
            manifest = validate_manifest(json.loads(row.manifest))
            folder = site_dir(row.id)
            if not folder.is_dir():
                raise InstallError("Die Plugin-Dateien fehlen (Datenordner nicht dauerhaft?). Bitte neu installieren")
            plugin = load_plugin(app, manifest, folder)
            logger.info("Installiertes Plugin geladen: %s %s (%s)", plugin.id, plugin.version, short_sha(row.sha))
        except Exception as exc:  # noqa: BLE001
            _errors[row.id] = str(exc) if isinstance(exc, (InstallError, ValueError)) else f"{type(exc).__name__}: {exc}"
            logger.warning("Installiertes Plugin %s nicht ladbar: %s", row.id, _errors[row.id])


# --- Install, update, remove ---

def _rmtree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def _package_dir(root: Path, folder: str, manifest: Dict[str, Any]) -> Path:
    package = (root / folder / manifest["package"]).resolve() if folder else (root / manifest["package"]).resolve()
    if not _under(package, root) or not package.is_dir():
        raise InstallError(f"Der Paketordner „{manifest['package']}“ liegt nicht im Repository")
    if not any((package / name).is_file() for name in ("pyproject.toml", "setup.py")):
        raise InstallError("Im Paketordner fehlt eine pyproject.toml")
    return package


def _install_dir(plugin_id: str, staging: Path, old: Path, keep_old: bool) -> None:
    """Swap the freshly installed site folder into place; the previous one moves to ``old``."""
    final = site_dir(plugin_id)
    if final.exists():
        _rmtree(old)
        os.replace(final, old)
    os.replace(staging, final)
    if not keep_old:
        _rmtree(old)


async def install_plugin(app: FastAPI, db: Session, user_id: Optional[int], url: str, sha: str,
                         values: Dict[str, Any]) -> Dict[str, Any]:
    """Install (or update to) exactly commit ``sha`` of the repository the link points to."""
    if not github.SHA_RE.match(sha or ""):
        raise InstallError("Ungültige Commit-Kennung")
    async with _lock:
        ref = github.parse_repo_url(url)
        _, folder = await github.resolve_sha(ref)
        manifest = parse_manifest(await github.fetch_manifest_bytes(ref, sha, folder, MANIFEST_FILE))
        plugin_id = manifest["id"]
        link = source_url(ref)
        row = check_installable(manifest, link, db)
        to_store = check_settings(manifest, values)
        base = prepare_dirs()
        tag = secrets.token_hex(4)
        tmp = base / "tmp" / f"{plugin_id}-{tag}"
        tmp.mkdir(parents=True)
        src = base / "src" / f"{plugin_id}-{sha}"
        staging = base / "site" / f".{plugin_id}.new-{tag}"
        old = base / "site" / f".{plugin_id}.old-{tag}"
        try:
            data = await github.download_tarball(ref.owner, ref.repo, sha)
            _rmtree(src)
            await asyncio.to_thread(archive.safe_extract, data, src)
            package = _package_dir(src, folder, manifest)
            await run_pip(package, staging, tmp)
            return await _activate(app, db, user_id, row, manifest, link, sha, to_store, staging, old)
        except BaseException:
            _rmtree(staging)
            if row is None or row.sha != sha:
                _rmtree(src)
            raise
        finally:
            _rmtree(tmp)


async def _activate(app, db, user_id, row, manifest, link, sha, to_store, staging, old) -> Dict[str, Any]:
    plugin_id = manifest["id"]
    update = row is not None
    old_manifest = validate_manifest(json.loads(row.manifest)) if update else None
    was_loaded = plugin_id in _loaded
    native = unload_plugin(app, plugin_id) if was_loaded else False
    _install_dir(plugin_id, staging, old, keep_old=update)
    try:
        plugin = load_plugin(app, manifest, site_dir(plugin_id))
    except BaseException:
        # Roll back: the previous version (if any) comes back, a first install leaves nothing behind
        unload_plugin(app, plugin_id)
        _rmtree(site_dir(plugin_id))
        if update and old.exists():
            os.replace(old, site_dir(plugin_id))
            if was_loaded:
                try:
                    load_plugin(app, old_manifest, site_dir(plugin_id))
                except Exception as exc:  # noqa: BLE001
                    _errors[plugin_id] = str(exc)
                    logger.warning("Vorherige Version von %s nicht ladbar: %s", plugin_id, exc)
        raise
    _rmtree(old)
    for stale in (plugins_dir() / "src").glob(f"{plugin_id}-*"):
        if stale.name != f"{plugin_id}-{sha}":
            _rmtree(stale)
    if plugin_id in settings.disabled_plugins:
        config_store.set_plugin_enabled(db, plugin_id, True)
    config_store.save_overrides(db, to_store)
    if row is None:
        row = InstalledPlugin(id=plugin_id)
        db.add(row)
    row.repo_url, row.sha, row.version = link, sha, manifest["version"]
    row.manifest = json.dumps(manifest, ensure_ascii=False)
    row.installed_by, row.installed_at, row.enabled = user_id, datetime.utcnow(), plugin_id not in settings.disabled_plugins
    db.commit()
    audit.warning("Plugin %s %s installiert (%s, Commit %s, Nutzer %s)", plugin_id, manifest["version"],
                  "Update" if update else "neu", short_sha(sha), user_id)
    return {"id": plugin_id, "version": manifest["version"], "sha": sha, "updated": update,
            "restart_required": native, "active": plugin.active}


async def remove_plugin(app: FastAPI, db: Session, user_id: Optional[int], plugin_id: str) -> Dict[str, Any]:
    async with _lock:
        row = db.get(InstalledPlugin, plugin_id)
        if row is None:
            raise LookupError(plugin_id)
        keys: List[str] = []
        try:
            keys = [s["key"] for s in json.loads(row.manifest).get("settings", [])]
        except (ValueError, AttributeError):
            pass
        native = unload_plugin(app, plugin_id)
        _errors.pop(plugin_id, None)
        config_store.delete_overrides(db, keys)
        if plugin_id in settings.disabled_plugins:
            config_store.set_plugin_enabled(db, plugin_id, True)  # a later install must not start switched off
        db.delete(row)
        db.commit()
        base = plugins_dir()
        await asyncio.to_thread(_rmtree, site_dir(plugin_id))
        for path in (base / "src").glob(f"{plugin_id}-*"):
            await asyncio.to_thread(_rmtree, path)
        audit.warning("Plugin %s entfernt (Nutzer %s)", plugin_id, user_id)
        return {"removed": True, "restart_required": native}


def installed_view(row: InstalledPlugin, lang: str) -> Dict[str, Any]:
    try:
        manifest = validate_manifest(json.loads(row.manifest))
        info = summary(manifest, lang)
    except ValueError:
        info = {"id": row.id, "name": row.id, "version": row.version, "description": "", "author": "",
                "homepage": "", "license": "", "min_hub_version": "", "hosts": [], "capabilities": []}
    plugin = plugin_registry.get(row.id)
    return {
        **info,
        "repo_url": row.repo_url,
        "sha": row.sha,
        "short_sha": short_sha(row.sha),
        "installed_at": row.installed_at.isoformat() if row.installed_at else None,
        "enabled": row.enabled,
        "loaded": row.id in _loaded,
        "active": bool(plugin and plugin.active),
        "error": i18n.translate(_errors[row.id], lang) if row.id in _errors else None,
    }
