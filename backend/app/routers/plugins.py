"""Install plugins from GitHub (admin only), analogous to the theme installer (``docs/plugins.md``).

- ``GET /api/plugins/installed``: installed plugins with their state, and whether the installer is switched on.
- ``POST /api/plugins/inspect``: link → manifest, commit and settings form (nothing is installed).
- ``POST /api/plugins/install``: install or update exactly the inspected commit.
- ``DELETE /api/plugins/{id}``: remove an installed plugin and its settings.

``PLUGIN_INSTALL_ENABLED=false`` switches inspect and install off.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.core.database import get_db
from app.core.i18n import request_language
from app.core.logging_config import get_logger
from app.core.security import require_min_role
from app.models.installed_plugin import InstalledPlugin
from app.models.user import ROLE_ADMIN, User
from app.plugins import installer
from app.plugins.manifest import ID_RE

logger = get_logger("router.plugins")
router = APIRouter(prefix="/api/plugins", tags=["plugins"])
admin_only = require_min_role(ROLE_ADMIN)


def _enabled() -> None:
    if not settings.plugin_install_enabled:
        raise HTTPException(403, "Die Plugin-Installation ist abgeschaltet (PLUGIN_INSTALL_ENABLED)")


class InspectRequest(BaseModel):
    url: str = Field(min_length=1, max_length=500)


class InstallRequest(InspectRequest):
    sha: str = Field(min_length=40, max_length=40)
    settings: Dict[str, Any] = Field(default_factory=dict, max_length=40)


@router.get("/installed")
async def installed(request: Request, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    lang = request_language(request)
    rows = db.query(InstalledPlugin).order_by(InstalledPlugin.id).all()
    return {
        "enabled": settings.plugin_install_enabled,
        "persistent": installer.data_dir_persistent(),
        "items": [installer.installed_view(r, lang) for r in rows],
    }


@router.post("/inspect")
async def inspect(data: InspectRequest, request: Request, db: Session = Depends(get_db),
                  _: User = Depends(admin_only)):
    _enabled()
    try:
        return await installer.inspect_plugin(data.url, request_language(request), db)
    except ValueError as exc:  # also GitHubError, InstallError
        raise HTTPException(422, str(exc)) from exc


@router.post("/install")
async def install(data: InstallRequest, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(admin_only)):
    _enabled()
    try:
        result = await installer.install_plugin(request.app, db, user.id, data.url, data.sha, data.settings)
    except ValueError as exc:  # also GitHubError, ArchiveError, InstallError
        raise HTTPException(422, str(exc)) from exc
    except OSError as exc:
        logger.warning("Plugin-Installation: Dateifehler: %s", exc.__class__.__name__)
        raise HTTPException(500, "Dateifehler bei der Installation. Einzelheiten stehen im Protokoll") from exc
    row = db.get(InstalledPlugin, result["id"])
    return {**result, "plugin": installer.installed_view(row, request_language(request))}


@router.delete("/{plugin_id}")
async def remove(plugin_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    if not ID_RE.match(plugin_id):
        raise HTTPException(404, "Plugin nicht gefunden")
    try:
        return await installer.remove_plugin(request.app, db, user.id, plugin_id)
    except LookupError as exc:
        raise HTTPException(404, "Plugin nicht gefunden") from exc
