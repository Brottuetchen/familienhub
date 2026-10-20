"""The small public API of the hub for plugins (``docs/plugins.md``, "Extension points").

``from app.plugins.api import notify`` sends a push notification to people of the family through the hub's
notification service: their quiet hours, their devices and their notification settings apply. All plugin
notifications share the category ``plugins``, which every person can switch off in the notification settings;
the history entry names the plugin as its source.

``proxy_image``: show an image that lives on an internal server (a photo library, a camera) without exposing the
server or its API key to the app. See ``docs/plugins.md``, "Data sources".

A buggy plugin must not flood a family, so every plugin may send a limited number of notifications per hour
(``RATE_LIMIT_PER_HOUR``, counted per call). Further calls are dropped (and logged) until the hour has passed.
"""

from __future__ import annotations

import hashlib
import time
from collections import deque
from typing import Any, Deque, Dict, Iterable, Mapping, Optional, Sequence

import httpx
from fastapi import HTTPException, Request, Response

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

DEFAULT_IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")


def sniff_image_type(head: bytes) -> Optional[str]:
    """Media type from the first bytes (magic numbers); the type the server claims is never trusted."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None


async def proxy_image(
    url: str,
    headers: Optional[Mapping[str, str]] = None,
    max_bytes: int = 5_000_000,
    allowed_types: Sequence[str] = DEFAULT_IMAGE_TYPES,
    *,
    request: Optional[Request] = None,
    timeout: float = 10.0,
    max_age: int = 86400,
    verify: bool = True,
) -> Response:
    """Fetch an image from ``url`` (with the plugin's own ``headers``, e.g. its API key) and return it as a response.

    Use it inside the plugin's own router (``/api/plugins/<id>/...``), which is authenticated by the hub, and build
    ``url`` yourself from settings and a path segment you validated. The app only ever sees the hub's address.

    - The type is checked by magic bytes against ``allowed_types``, not by the ``Content-Type`` of the server.
    - At most ``max_bytes`` are read; larger images are refused (413). Redirects are not followed.
    - The answer carries ``Cache-Control: private, max-age=<max_age>`` and an ``ETag``; pass ``request`` to answer a
      matching ``If-None-Match`` with 304.
    - Failures raise ``HTTPException`` with a short text that never contains the address or the headers:
      404 (not found there), 413 (too large), 415 (not an allowed image), 502 (unreachable, timeout, other error).
    """
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(502, "Bildquelle nicht erreichbar")
    chunks = []
    size = 0
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, verify=verify) as client:
            async with client.stream("GET", url, headers=dict(headers or {})) as upstream:
                if upstream.status_code == 404:
                    raise HTTPException(404, "Bild nicht gefunden")
                if upstream.status_code != 200:
                    logger.warning("Image proxy: upstream answered HTTP %d", upstream.status_code)
                    raise HTTPException(502, "Bildquelle nicht erreichbar")
                declared = upstream.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > max_bytes:
                    raise HTTPException(413, "Bild zu groß")
                async for chunk in upstream.aiter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise HTTPException(413, "Bild zu groß")
                    chunks.append(chunk)
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        logger.warning("Image proxy failed: %s", type(exc).__name__)  # never log the address, it may hold a key
        raise HTTPException(502, "Bildquelle nicht erreichbar") from exc
    body = b"".join(chunks)
    media_type = sniff_image_type(body[:16])
    if media_type is None or media_type not in allowed_types:
        raise HTTPException(415, "Kein erlaubtes Bildformat")
    etag = '"' + hashlib.sha1(body).hexdigest()[:24] + '"'  # noqa: S324 - cache validator, not security
    cache = {"Cache-Control": f"private, max-age={int(max_age)}", "ETag": etag, "X-Content-Type-Options": "nosniff"}
    if request is not None and request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=cache)
    return Response(content=body, media_type=media_type, headers=cache)
