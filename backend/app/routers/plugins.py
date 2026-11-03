"""Install plugins from GitHub (admin only), analogous to the theme installer (``docs/plugins.md``).

- ``GET /api/plugins/installed``: installed plugins with their state, and whether the installer is switched on.
- ``POST /api/plugins/inspect``: link → manifest, commit and settings form (nothing is installed).
- ``POST /api/plugins/install``: install or update exactly the inspected commit.
- ``DELETE /api/plugins/{id}``: remove an installed plugin and its settings.
- ``GET /api/plugins/personal-settings``, ``GET|PUT /api/plugins/{id}/personal-settings`` and
  ``POST /api/plugins/{id}/personal-settings/test``: the logged-in person's own settings of active plugins
  (secrets only as set / not set).

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
from app.models.user import ROLE_ADMIN, ROLE_CHILD, User
from app.plugins import installer
from app.plugins.hooks import run_test_personal_settings
from app.plugins.manifest import ID_RE
from app.plugins.registry import plugin_registry
from app.services import personal_settings

logger = get_logger("router.plugins")
router = APIRouter(prefix="/api/plugins", tags=["plugins"])
admin_only = require_min_role(ROLE_ADMIN)
# Connecting an own account is for children and up, like the Nextcloud and Habitica accounts
person_only = require_min_role(ROLE_CHILD)


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


def _personal_view(plugin, db: Session, user: User) -> Dict[str, Any]:
    return {"id": plugin.id, "name": plugin.name, "description": plugin.description,
            "has_test": plugin.has_personal_test, "fields": personal_settings.form(db, plugin, user.id)}


def _personal_plugin(plugin_id: str):
    plugin = plugin_registry.get(plugin_id) if ID_RE.match(plugin_id) else None
    if plugin is None or not plugin.active or not plugin.personal_settings:
        raise HTTPException(404, "Plugin nicht gefunden")
    return plugin


class PersonalValues(BaseModel):
    values: Dict[str, Any] = Field(default_factory=dict, max_length=40)


@router.get("/personal-settings")
async def personal_overview(db: Session = Depends(get_db), user: User = Depends(person_only)):
    """Active plugins with settings of their own for this person, with the form and their current values."""
    return {"items": [_personal_view(p, db, user) for p in plugin_registry.all() if p.active and p.personal_settings]}


@router.get("/{plugin_id}/personal-settings")
async def personal_get(plugin_id: str, db: Session = Depends(get_db), user: User = Depends(person_only)):
    return _personal_view(_personal_plugin(plugin_id), db, user)


@router.put("/{plugin_id}/personal-settings")
async def personal_put(plugin_id: str, data: PersonalValues, db: Session = Depends(get_db),
                       user: User = Depends(person_only)):
    """Saves the sent values for this person. A secret left empty keeps the stored one."""
    plugin = _personal_plugin(plugin_id)
    try:
        personal_settings.save(db, plugin, user.id, data.values)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _personal_view(plugin, db, user)


@router.post("/{plugin_id}/personal-settings/test")
async def personal_test(plugin_id: str, data: PersonalValues, db: Session = Depends(get_db),
                        user: User = Depends(person_only)):
    """The plugin's own test with the typed, not yet saved values (empty secret = stored one)."""
    plugin = _personal_plugin(plugin_id)
    try:
        values = personal_settings.resolve(db, plugin, user.id, data.values)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    result = await run_test_personal_settings(plugin, user, values)
    return result or {"ok": True, "level": "info", "message": "Dieses Plugin bietet keinen Test an"}


@router.delete("/{plugin_id}")
async def remove(plugin_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    if not ID_RE.match(plugin_id):
        raise HTTPException(404, "Plugin nicht gefunden")
    try:
        return await installer.remove_plugin(request.app, db, user.id, plugin_id)
    except LookupError as exc:
        raise HTTPException(404, "Plugin nicht gefunden") from exc
