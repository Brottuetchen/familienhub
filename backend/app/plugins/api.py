"""The small public API of the hub for plugins (``docs/plugins.md``, "Extension points").

``from app.plugins.api import notify`` sends a push notification to people of the family through the hub's
notification service: their quiet hours, their devices and their notification settings apply. All plugin
notifications share the category ``plugins``, which every person can switch off in the notification settings;
the history entry names the plugin as its source.

A buggy plugin must not flood a family, so every plugin may send a limited number of notifications per hour
(``RATE_LIMIT_PER_HOUR``, counted per call). Further calls are dropped (and logged) until the hour has passed.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any, Deque, Dict, Iterable, Optional

from app.core.logging_config import get_logger
from app.plugins.hooks import _clean, valid_link

logger = get_logger("plugins.api")

CATEGORY = "plugins"
RATE_LIMIT_PER_HOUR = 20
WINDOW_SECONDS = 3600
MAX_RECIPIENTS = 50
MAX_TITLE, MAX_BODY = 100, 500
MAX_DATA_KEYS, MAX_DATA_VALUE = 10, 200
# Keys the hub itself puts into a notification's data; a plugin cannot set them
RESERVED_DATA = {"notification_id", "actions", "action_token", "reminder_id", "category", "title", "body", "url", "route"}

_sent: Dict[str, Deque[float]] = {}


def reset_limits() -> None:
    """Forget the rate-limit counters (tests)."""
    _sent.clear()


def _allow(plugin_id: str) -> bool:
    now = time.monotonic()
    window = _sent.setdefault(plugin_id, deque())
    while window and now - window[0] > WINDOW_SECONDS:
        window.popleft()
    if len(window) >= RATE_LIMIT_PER_HOUR:
        return False
    window.append(now)
    return True


def _route(value: Any) -> Optional[str]:
    """An in-app path such as ``/shopping``; anything else is dropped."""
    if isinstance(value, str) and value.startswith("/") and not value.startswith("//") and len(value) <= 100 \
            and not any(c <= " " for c in value):
        return value
    return None


def _payload(url: Optional[str], data: Optional[Dict[str, Any]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key, value in (data or {}).items():
        if len(out) >= MAX_DATA_KEYS:
            break
        if not isinstance(key, str) or key in RESERVED_DATA or not isinstance(value, (str, int, float, bool)):
            continue
        text = _clean(str(value), MAX_DATA_VALUE)
        if text is not None:
            out[key[:40]] = text
    link = valid_link(url)
    if link:
        out["url"] = link
    route = _route((data or {}).get("route"))
    if route:
        out["route"] = route
    return out


def _recipients(db, user_ids: Optional[Iterable[int]], roles: Optional[Iterable[str]]) -> list:
    from app.models.user import User

    wanted_ids = {int(i) for i in (user_ids or []) if isinstance(i, int) and not isinstance(i, bool)}
    wanted_roles = {str(r).lower() for r in (roles or [])}
    if not wanted_ids and not wanted_roles:
        return []
    users = []
    for u in db.query(User).filter(User.is_active == True).order_by(User.id).all():  # noqa: E712
        role = (u.role or "").lower()
        if (u.id in wanted_ids or "all" in wanted_roles or role in wanted_roles
                or ("admin" in wanted_roles and u.is_admin)):
            users.append(u)
    return users[:MAX_RECIPIENTS]


async def notify(plugin_id: str, *, user_ids: Optional[Iterable[int]] = None, roles: Optional[Iterable[str]] = None,
                 title: str, body: str = "", url: Optional[str] = None,
                 data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Pushes ``title``/``body`` to the given people (``user_ids``) and/or everyone with one of the ``roles``
    (``"admin"``, ``"partner"``, ``"child"``, ``"guest"``, or ``"all"`` for every active person).

    ``url`` (https only) is attached for the app to open; ``data`` takes up to 10 short text values (a key
    ``route`` with an in-app path such as ``/shopping`` opens that screen). Without recipients nothing is sent.

    Fails softly and never raises: returns ``{"recipients": n, "delivered": n, "sent": bool, "reason": …}``
    where ``reason`` is ``"inactive"``, ``"no_recipients"``, ``"invalid"`` or ``"rate_limited"`` if nothing was sent.
    """
    from app.core.database import SessionLocal
    from app.plugins.registry import plugin_registry
    from app.services.notify import notify as hub_notify

    def skipped(reason: str) -> Dict[str, Any]:
        return {"recipients": 0, "delivered": 0, "sent": False, "reason": reason}

    plugin = plugin_registry.get(plugin_id) if isinstance(plugin_id, str) else None
    if plugin is None or not plugin.active:
        return skipped("inactive")
    clean_title, clean_body = _clean(title, MAX_TITLE), _clean(body, MAX_BODY) or ""
    if clean_title is None:
        return skipped("invalid")
    try:
        with SessionLocal() as db:
            people = _recipients(db, user_ids, roles)
        if not people:
            return skipped("no_recipients")
        if not _allow(plugin_id):
            logger.warning("Plugin %s: notification dropped, limit of %d per hour reached", plugin_id,
                           RATE_LIMIT_PER_HOUR)
            return skipped("rate_limited")
        payload = _payload(url, data)
        delivered = 0
        for person in people:
            try:
                delivered += await hub_notify(person.id, clean_title, clean_body, data=dict(payload),
                                              category=CATEGORY, source=f"plugin:{plugin_id}")
            except Exception as exc:  # noqa: BLE001 - one unreachable person must not stop the others
                logger.warning("Plugin %s: notification to user %s failed: %s", plugin_id, person.id,
                               type(exc).__name__)
        return {"recipients": len(people), "delivered": delivered, "sent": True, "reason": None}
    except Exception as exc:  # noqa: BLE001 - the API never raises into a plugin's job
        logger.warning("Plugin %s: notify failed: %s", plugin_id, type(exc).__name__)
        return skipped("error")
