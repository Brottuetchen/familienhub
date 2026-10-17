"""Verwaltung (nur Admins): Systemübersicht, Familie & Verbindungen, Haus-Geräte, Protokoll.

Liefert nur, was ein Admin zum Einrichten braucht: keine Tokens, keine Inhalte aus den Diensten.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import __version__
from app.config import settings
from app.core import log_buffer
from app.core.database import get_db
from app.core.security import require_min_role
from app.models.caldav import CalDAVAccount
from app.models.habitica import HabiticaAccount
from app.models.paperless import PaperlessAccount
from app.models.push_device import PushDevice
from app.models.user import ROLE_ADMIN, User
from app.plugins.registry import plugin_registry

router = APIRouter(prefix="/api/admin", tags=["admin"])
admin_only = require_min_role(ROLE_ADMIN)

HEALTH_TTL = 30
_health_cache: Dict[str, tuple] = {}


async def _check(url: str) -> Dict[str, Any]:
    """Nur Erreichbarkeit (keine Anmeldung, keine Daten). Fehlertexte ohne Adressen."""
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
            r = await client.get(url)
    except httpx.TimeoutException:
        return {"status": "error", "message": "Zeitüberschreitung"}
    except httpx.HTTPError:
        return {"status": "error", "message": "Nicht erreichbar"}
    ms = round((time.monotonic() - started) * 1000)
    if r.status_code >= 500:
        return {"status": "error", "message": f"Antwortet mit Fehler {r.status_code}", "latency_ms": ms}
    return {"status": "ok", "message": "Erreichbar", "latency_ms": ms}


async def _health(plugin) -> Dict[str, Any]:
    if not plugin.active:
        return {"status": "off", "message": "Aus" if plugin.is_configured() else "Nicht eingerichtet"}
    url = plugin.health_url()
    if not url:
        return {"status": "unknown", "message": "Keine Prüfung möglich"}
    hit = _health_cache.get(plugin.id)
    if hit and hit[0] == url and time.monotonic() - hit[1] < HEALTH_TTL:
        return hit[2]
    result = await _check(url)
    _health_cache[plugin.id] = (url, time.monotonic(), result)
    return result


@router.get("/overview")
async def overview(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    """Server, Plugins mit Erreichbarkeit, Push, Nutzerzahlen."""
    plugins = plugin_registry.all()
    health = await asyncio.gather(*(_health(p) for p in plugins))
    devices = dict(db.query(PushDevice.kind, func.count(PushDevice.id)).group_by(PushDevice.kind).all())
    return {
        "server": {"version": __version__, "environment": settings.environment},
        "plugins": [{
            "id": p.id, "name": p.name, "description": p.description,
            "active": p.active, "configured": p.is_configured(), "missing": p.missing_settings(),
            "health": h,
        } for p, h in zip(plugins, health)],
        "push": {
            "fcm": bool(settings.fcm_service_account_file and settings.fcm_project_id),
            "webpush": bool(settings.vapid_private_key and settings.vapid_public_key),
            "devices": {"fcm": devices.get("fcm", 0), "webpush": devices.get("webpush", 0)},
        },
        "users": {
            "active": db.query(User).filter(User.is_active == True).count(),  # noqa: E712
            "total": db.query(User).count(),
        },
    }


async def _seerr_links(users: List[User]) -> Dict[int, Optional[bool]]:
    plugin = plugin_registry.get("seerr")
    if not plugin or not plugin.active:
        return {}
    from app.routers import media

    out: Dict[int, Optional[bool]] = {}
    for u in users:
        try:
            await media._seerr_id(u)
            out[u.id] = True
        except media.NoAccount:
            out[u.id] = False
        except media.SeerrError:
            out[u.id] = None  # gerade nicht prüfbar
    return out


@router.get("/users")
async def users(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    """Familie mit Rolle und Verbindungen (nur ob verbunden, nie Zugangsdaten)."""
    people = db.query(User).order_by(User.id).all()
    ids_with = lambda model: {row[0] for row in db.query(model.user_id).all()}  # noqa: E731
    caldav, habitica, paperless = ids_with(CalDAVAccount), ids_with(HabiticaAccount), ids_with(PaperlessAccount)
    devices = dict(db.query(PushDevice.user_id, func.count(PushDevice.id)).group_by(PushDevice.user_id).all())
    seerr = await _seerr_links([u for u in people if u.is_active])
    active = {p.id for p in plugin_registry.all() if p.active}
    out = []
    for u in people:
        links = {}
        if "nextcloud" in active:
            links["nextcloud"] = u.id in caldav
        if "habitica" in active:
            links["habitica"] = u.id in habitica
        if "paperless" in active:
            links["paperless"] = u.id in paperless
        if u.id in seerr:
            links["seerr"] = seerr[u.id]
        out.append({
            "id": u.id, "username": u.username, "display_name": u.effective_name, "email": u.email,
            "role": u.role, "is_active": u.is_active,
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "avatar_color": u.avatar_color, "avatar_url": u.avatar_url,
            "devices": devices.get(u.id, 0), "links": links,
        })
    return out


# Domains, die auf der Haus-Karte sinnvoll sind (Anzeige); schaltbar sind nur diese vier
SHOWABLE = {"light", "switch", "scene", "script", "sensor", "binary_sensor", "climate", "cover", "lock",
            "media_player", "fan", "vacuum", "input_boolean", "person", "device_tracker", "weather", "water_heater"}
CONTROLLABLE = {"light", "switch", "scene", "script"}


@router.get("/house/entities")
async def house_entities(_: User = Depends(admin_only)):
    """HA-Entitäten zur Auswahl (Name, Bereich, Zustand) und die aktuelle Auswahl."""
    from app.connectors.homeassistant_connector import HomeAssistantConnector, house_entities, house_write_entities

    def selection(fn, value):
        try:
            return fn(value or "")
        except ValueError:
            return []

    current = {
        "display": selection(house_entities, settings.ha_house_entities),
        "control": selection(house_write_entities, settings.ha_house_write_entities),
        "max": 6,
    }
    connector = HomeAssistantConnector()
    if not connector.is_configured:
        return {"status": "not_configured", "items": [], "selection": current}
    try:
        states = await connector._get_json("/api/states")
    except Exception:
        return {"status": "unavailable", "items": [], "selection": current}
    items = []
    for s in states if isinstance(states, list) else []:
        entity = str(s.get("entity_id", ""))
        domain = entity.split(".")[0]
        if domain not in SHOWABLE:
            continue
        attrs = s.get("attributes") or {}
        unit = attrs.get("unit_of_measurement")
        items.append({
            "entity_id": entity,
            "name": attrs.get("friendly_name") or entity,
            "domain": domain,
            "state": s.get("state"),
            "unit": unit if isinstance(unit, str) else None,
            "controllable": domain in CONTROLLABLE,
        })
    items.sort(key=lambda i: (i["domain"], str(i["name"]).lower()))
    return {"status": "ok", "items": items[:1000], "selection": current}


@router.get("/log")
async def log(_: User = Depends(admin_only)):
    """Letzte Warnungen und Fehler seit dem Start (geschwärzt)."""
    return {"items": log_buffer.entries()}
