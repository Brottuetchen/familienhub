"""Admin: Plugin-Einstellungen (Zugänge) im UI verwalten.

Nur für Admins. Secrets werden nie im Klartext zurückgegeben (nur ``is_set``);
gespeicherte Werte greifen sofort (kein Neustart).
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_min_role
from app.models.user import ROLE_ADMIN, User
from app.plugins.base import get_setting
from app.plugins.registry import plugin_registry
from app.services import config_store

router = APIRouter(prefix="/api/admin", tags=["admin"])


class SettingsUpdate(BaseModel):
    values: Dict[str, str]


def _view(plugin) -> Dict[str, Any]:
    info = plugin.describe()
    fields = []
    for s in plugin.settings:
        cur = get_setting(s.key) or ""
        fields.append({
            "key": s.key, "label": s.label, "secret": s.secret, "required": s.required, "help": s.help,
            "value": "" if s.secret else str(cur),  # Secrets nie zurückgeben
            "is_set": bool(cur),
        })
    info["fields"] = fields
    info.pop("settings", None)
    return info


@router.get("/settings")
async def get_settings(current_user: User = Depends(require_min_role(ROLE_ADMIN))):
    """Alle Plugins mit ihren Einstellungen (Secrets maskiert)."""
    return [_view(p) for p in plugin_registry.all() if p.settings]


@router.put("/settings")
async def update_settings(
    data: SettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(ROLE_ADMIN)),
):
    """Einstellungen speichern (Secrets verschlüsselt) und sofort anwenden."""
    from app.connectors.homeassistant_connector import house_entities, house_write_entities

    for key, value in data.values.items():
        if key.upper() in {"HA_HOUSE_ENTITIES", "HA_HOUSE_WRITE_ENTITIES"}:
            try:
                (house_write_entities if key.upper() == "HA_HOUSE_WRITE_ENTITIES" else house_entities)(value)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
    config_store.save_overrides(db, data.values)
    from app.routers import admin_panel

    admin_panel._health_cache.clear()  # the overview must show the new state right away
    return {"saved": True, "plugins": [_view(p) for p in plugin_registry.all() if p.settings]}


class PluginToggle(BaseModel):
    enabled: bool


@router.put("/plugins/{plugin_id}")
async def toggle_plugin(
    plugin_id: str,
    data: PluginToggle,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(ROLE_ADMIN)),
):
    """Plugin an- oder abschalten. Abgeschaltete Plugins verschwinden aus /api/modules."""
    plugin = plugin_registry.get(plugin_id)
    if plugin is None:
        raise HTTPException(status_code=404, detail="Plugin nicht gefunden")
    config_store.set_plugin_enabled(db, plugin_id, data.enabled)
    return _view(plugin)
