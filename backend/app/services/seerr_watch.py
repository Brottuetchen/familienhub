"""Polls Seerr for requests that became available and notifies whoever asked for them.

Seerr has a single webhook slot, which is often taken (e.g. by a Jellyfin plugin). Polling needs no change in
Seerr. The webhook (`/api/media/webhook`) still works and shares the "already reported" table.
"""

from __future__ import annotations

from typing import Dict

from app.core.database import SessionLocal
from app.core.logging_config import get_logger
from app.models.seerr_notice import SeerrNotice
from app.models.user import User
from app.services.notify import notify

logger = get_logger("service.seerr_watch")

AVAILABLE = 5  # Seerr media status "available" (4 = partially, e.g. some seasons)


def remember(db, request_id: int) -> bool:
    """Marks a request as reported; False if it already was."""
    if db.get(SeerrNotice, request_id) is not None:
        return False
    db.add(SeerrNotice(request_id=request_id))
    db.commit()
    return True


async def check_available() -> int:
    """One pass; returns how many people were notified."""
    from app.routers import media

    if not media._active():
        return 0
    try:
        data = await media._seerr("GET", "/request", params={"take": 100, "skip": 0, "filter": "available", "sort": "modified"})
    except media.SeerrError:
        logger.info("Seerr nicht erreichbar, nächster Versuch später")
        return 0
    requests = [r for r in (data or {}).get("results", []) if isinstance(r, dict) and isinstance(r.get("id"), int)]
    sent = 0
    with SessionLocal() as db:
        if db.get(SeerrNotice, 0) is None:  # first run: what is available now was reported elsewhere before
            for r in requests:
                if db.get(SeerrNotice, r["id"]) is None:
                    db.add(SeerrNotice(request_id=r["id"]))
            db.add(SeerrNotice(request_id=0))
            db.commit()
            return 0
        fresh = [r for r in requests if db.get(SeerrNotice, r["id"]) is None
                 and (r.get("media") or {}).get("status") == AVAILABLE]
        if not fresh:
            return 0
        hub_by_seerr: Dict[int, int] = {}
        for u in db.query(User).filter(User.is_active == True).all():  # noqa: E712
            try:
                hub_by_seerr.setdefault(await media._seerr_id(u), u.id)
            except (media.NoAccount, media.SeerrError):
                continue
        for r in fresh:
            remember(db, r["id"])  # also when nobody matches: never report the same request later
            seerr_user = (r.get("requestedBy") or {}).get("id")
            hub_user = hub_by_seerr.get(seerr_user)
            if hub_user is None:
                continue
            m = r.get("media") or {}
            kind = "tv" if (m.get("mediaType") or r.get("type")) == "tv" else "movie"
            meta = await media._meta(kind, m.get("tmdbId"), seerr_user) if m.get("tmdbId") else {}
            title = meta.get("title") or ("Serie" if kind == "tv" else "Film")
            await notify(hub_user, f"🎬 „{title}“ ist da", "Jetzt in Jellyfin.", data={"route": "/media"},
                         category="media", source="Seerr")
            sent += 1
    return sent
