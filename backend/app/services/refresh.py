"""Stille Aktualisierungs-Pushes: Geräte laden „Heute“/Einkauf neu und aktualisieren die Widgets.

Kurz hintereinander eintreffende Änderungen werden gebündelt (DEBOUNCE) und höchstens alle
MIN_INTERVAL Sekunden verschickt. Die Nachricht enthält keine Inhalte, nur „neu laden“.
"""

from __future__ import annotations

import asyncio
import time
from typing import Iterable, Optional, Set

import httpx

from app.config import settings
from app.core.database import SessionLocal
from app.core.logging_config import get_logger

logger = get_logger("service.refresh")

SCOPES = ("shopping", "tasks", "meals", "reminders", "external")
DEBOUNCE = 3.0
MIN_INTERVAL = 15.0

_pending: Set[str] = set()
_task: Optional[asyncio.Task] = None
_last_sent = 0.0


def _reset() -> None:
    global _task, _last_sent
    _pending.clear()
    _task = None
    _last_sent = 0.0


def refresh_message(token: str, scopes: Iterable[str]) -> dict:
    """Reine Datennachricht ohne Anzeige; HIGH, damit Android die App kurz im Hintergrund weckt."""
    return {"token": token, "data": {"type": "refresh", "scope": ",".join(sorted(scopes))},
            "android": {"priority": "HIGH"}}


async def _send_refresh(scopes: Set[str]) -> None:
    from app.models.push_device import PushDevice
    from app.models.user import User
    from app.services.notify import _notify_service

    if not _notify_service.fcm_configured:
        return
    token = _notify_service._get_fcm_token()
    if not token:
        return
    with SessionLocal() as db:
        devices = (
            db.query(PushDevice)
            .join(User, User.id == PushDevice.user_id)
            .filter(PushDevice.kind == "fcm", User.is_active == True)  # noqa: E712
            .all()
        )
        targets = [d.token for d in devices]
    async with httpx.AsyncClient(timeout=10) as client:
        for device_token in targets:
            try:
                resp = await client.post(
                    f"https://fcm.googleapis.com/v1/projects/{settings.fcm_project_id}/messages:send",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"message": refresh_message(device_token, scopes)},
                )
                if resp.status_code != 200:
                    logger.info("refresh push nicht zugestellt: %s", resp.status_code)
            except httpx.HTTPError as exc:
                logger.info("refresh push fehlgeschlagen: %s", exc)


async def _flush() -> None:
    global _task, _last_sent
    try:
        await asyncio.sleep(DEBOUNCE)
        wait = MIN_INTERVAL - (time.monotonic() - _last_sent)
        if _last_sent and wait > 0:
            await asyncio.sleep(wait)
        scopes = set(_pending)
        _pending.clear()
        _last_sent = time.monotonic()
        if scopes:
            await _send_refresh(scopes)
    except Exception as exc:  # noqa: BLE001 – Widgets-Aktualisierung darf nie etwas anderes stören
        logger.warning("refresh push: %s", exc)
    finally:
        _task = None
        if _pending:  # während des Versands neu hinzugekommen
            schedule_refresh(next(iter(_pending)))


def _enabled() -> bool:
    """Nur mit eingerichtetem FCM (Android-Geräte); Web-Push-Geräte haben keine Widgets."""
    from app.services.notify import _notify_service

    return _notify_service.fcm_configured


def schedule_refresh(scope: str) -> None:
    """Merkt eine Änderung vor; braucht eine laufende Event-Loop (Request-Kontext)."""
    global _task
    if not _enabled():
        return
    _pending.add(scope)
    if _task is None or _task.done():
        try:
            _task = asyncio.get_running_loop().create_task(_flush())
        except RuntimeError:
            logger.debug("refresh ohne Event-Loop übersprungen")


# Pfad-Präfix → Bereich. Nur Änderungen an Daten, die Widgets/Heute zeigen.
PATH_SCOPES = (
    ("/api/shopping", "shopping"),
    ("/api/voice/shopping", "shopping"),
    ("/api/voice/tasks", "tasks"),
    ("/api/voice/reminders", "reminders"),
    ("/api/tasks", "tasks"),
    ("/api/meals", "meals"),
    ("/api/cookidoo/plan", "meals"),
    ("/api/reminders", "reminders"),
    ("/api/paperless/deadlines", "reminders"),  # Frist → Erinnerung
)


def scope_for(method: str, path: str, status: int) -> Optional[str]:
    if method not in ("POST", "PUT", "PATCH", "DELETE") or not 200 <= status < 300:
        return None
    if path.startswith("/api/tasks/me/"):
        return None  # eigene Kontoeinstellungen, keine Aufgabendaten
    for prefix, scope in PATH_SCOPES:
        if path == prefix or path.startswith(prefix + "/"):
            return scope
    return None
