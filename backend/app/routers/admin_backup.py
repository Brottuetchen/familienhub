"""Administration → Backup: download, store, restore and schedule backups (admin only).

See ``app/services/backup.py`` for the archive format and the restore rules. Operational problems come
back as ``{"ok": false, "code": ..., "message": ...}`` (the app translates the code) instead of errors.
"""

from __future__ import annotations

import secrets as _secrets
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app import __version__
from app.config import settings
from app.core.database import get_db
from app.core.logging_config import get_logger
from app.core.security import ALGORITHM, require_min_role
from app.models.user import ROLE_ADMIN, User
from app.services import backup as svc
from app.services import config_store

logger = get_logger("router.admin_backup")
router = APIRouter(prefix="/api/admin/backup", tags=["admin"])
admin_only = require_min_role(ROLE_ADMIN)

LINK_SECONDS = 120
_used_links: Dict[str, float] = {}  # jti -> expiry; a download link works once


def _overview() -> Dict[str, Any]:
    from app.core.database import engine

    status = svc.read_status()
    return {
        "last": {"at": status.get("last_at"), "ok": status.get("last_ok"), "kind": status.get("last_kind"),
                 "name": status.get("last_name"), "error": status.get("last_error")},
        "last_restore_at": status.get("last_restore_at"),
        "auto": svc.auto_enabled(),
        "keep": svc.keep_count(),
        "auto_time": f"{svc.AUTO_HOUR:02d}:{svc.AUTO_MINUTE:02d}",
        "dialect": engine.dialect.name,
        "version": __version__,
        "backups": svc.list_backups(),
    }


@router.get("")
def get_backup(_: User = Depends(admin_only)):
    return _overview()


class CreateBody(BaseModel):
    include_keys: bool = True


@router.post("")
def create(data: CreateBody, user: User = Depends(admin_only)):
    """Create a backup and keep it in the data folder (``<DATA_DIR>/backups``)."""
    logger.info("audit: %s creates a backup", user.username)
    return svc.create_backup("manual", include_keys=data.include_keys)


class SettingsBody(BaseModel):
    auto: bool
    keep: int = Field(ge=1, le=60)


@router.put("/settings")
def put_settings(data: SettingsBody, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    config_store.save_overrides(db, {"BACKUP_AUTO": "true" if data.auto else "false", "BACKUP_KEEP": str(data.keep)})
    logger.info("audit: %s set nightly backup=%s keep=%d", user.username, data.auto, data.keep)
    return _overview()


@router.delete("/{name}")
def delete(name: str, user: User = Depends(admin_only)):
    try:
        svc.delete_backup(name)
    except svc.BackupError as exc:
        return {"ok": False, "code": exc.code, "message": exc.message}
    logger.info("audit: %s deleted backup %s", user.username, name)
    return {"ok": True}


# --- Download: a short-lived, single-use link, because a browser download cannot send the sign-in header ---

class LinkBody(BaseModel):
    include_keys: bool = True


@router.post("/download-link")
def download_link(data: LinkBody, user: User = Depends(admin_only)):
    now = time.time()
    for jti in [j for j, exp in _used_links.items() if exp < now]:
        _used_links.pop(jti, None)
    token = jwt.encode({"typ": "backup_download", "uid": user.id, "keys": data.include_keys, "jti": uuid.uuid4().hex,
                        "exp": datetime.utcnow() + timedelta(seconds=LINK_SECONDS)},
                       settings.secret_key, algorithm=ALGORITHM)
    return {"path": f"/api/admin/backup/download?token={token}", "expires_in": LINK_SECONDS}


@router.get("/download")
def download(token: str, db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="The download link expired") from None
    jti = str(payload.get("jti") or "")
    user = db.get(User, payload.get("uid")) if payload.get("typ") == "backup_download" else None
    if user is None or not user.is_active or not (user.is_admin or user.role == ROLE_ADMIN) or not jti \
            or jti in _used_links:
        raise HTTPException(status_code=401, detail="The download link expired")
    _used_links[jti] = time.time() + LINK_SECONDS
    if not svc._lock.acquire(blocking=False):  # noqa: SLF001
        raise HTTPException(status_code=409, detail="Another backup or restore is running")
    tmp = None
    try:
        base = svc._ensure_dir()  # noqa: SLF001
        tmp = base / f".download-{_secrets.token_hex(8)}.tmp"
        manifest = svc.create_archive(tmp, include_keys=bool(payload.get("keys", True)))
        svc._write_status(last_at=manifest["created_at"], last_kind="download", last_ok=True,  # noqa: SLF001
                          last_name=None, last_size=tmp.stat().st_size, last_error=None)
    except Exception as exc:  # noqa: BLE001
        svc._fail("download", "failed", type(exc).__name__)  # noqa: SLF001
        if tmp is not None:
            tmp.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="The backup failed. See the hub log") from None
    finally:
        svc._lock.release()  # noqa: SLF001
    logger.info("audit: %s downloaded a backup", user.username)
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return FileResponse(tmp, media_type="application/zip", filename=f"familienhub-backup-{stamp}.zip",
                        background=BackgroundTask(lambda: tmp.unlink(missing_ok=True)))


# --- Restore ---

@router.post("/upload")
async def upload(request: Request, user: User = Depends(admin_only)):
    """Raw upload (``Content-Type: application/octet-stream``) of a backup file; it is checked, not restored."""
    logger.info("audit: %s uploads a backup file", user.username)
    try:
        part = svc.upload_part_path()
    except svc.BackupError as exc:
        return {"ok": False, "code": exc.code, "message": exc.message}
    size = 0
    try:
        with open(part, "wb") as fh:
            async for chunk in request.stream():
                size += len(chunk)
                if size > svc.MAX_TOTAL_BYTES:
                    part.unlink(missing_ok=True)
                    return {"ok": False, "code": "unsafe", "message": "The file is unreasonably large"}
                fh.write(chunk)
        return {"ok": True, **await run_in_threadpool(svc.finish_upload, part)}
    except svc.BackupError as exc:
        return {"ok": False, "code": exc.code, "message": exc.message}
    except OSError:
        part.unlink(missing_ok=True)
        return {"ok": False, "code": "dir_not_writable",
                "message": "The data folder is not writable. Mount a volume at /app/data"}


@router.post("/{name}/inspect")
def inspect(name: str, _: User = Depends(admin_only)):
    return svc.inspect_backup(name)


class RestoreBody(BaseModel):
    confirm: bool = False


@router.post("/{name}/restore")
def restore(name: str, data: RestoreBody, user: User = Depends(admin_only)):
    """Replace ALL data of the hub with this backup. Needs ``confirm: true``; the hub must be restarted afterwards."""
    if not data.confirm:
        raise HTTPException(status_code=422, detail="Restoring needs an explicit confirmation")
    logger.warning("audit: %s starts a restore from %s", user.username, name)
    return svc.restore_backup(name)
