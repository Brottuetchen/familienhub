"""Welche Bereiche die App zeigen soll (aus Kern + aktiven Plugins)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.models.user import User
from app.plugins.registry import plugin_registry

router = APIRouter(prefix="/api", tags=["system"])

# Immer vorhanden (Kern)
CORE_MODULES = ("today", "reminders", "meals")
# Von Plugins geliefert
PLUGIN_MODULES = ("tasks", "calendar", "shopping", "books", "weather", "meal_source", "meal_planning", "documents", "media_requests")


@router.get("/modules")
async def modules(_: User = Depends(get_current_user)):
    out = {m: {"enabled": True, "core": True, "plugin": None} for m in CORE_MODULES}
    for cap in PLUGIN_MODULES:
        provider = plugin_registry.provider(cap)
        out[cap] = {"enabled": provider is not None, "core": False, "plugin": provider.id if provider else None}
        if cap == "tasks":
            out[cap]["providers"] = [p.id for p in plugin_registry.providers(cap)]
    return {
        "modules": out,
        "plugins": [
            {k: v for k, v in p.describe().items() if k not in ("settings", "missing_settings")}
            for p in plugin_registry.all()
        ],
    }
