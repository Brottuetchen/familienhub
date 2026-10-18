"""Filme und Serien wünschen über Seerr (#31).

Der Hub nutzt den Seerr-API-Schlüssel und handelt per `X-Api-User` als der passende Seerr-Nutzer.
Seerr prüft damit Rechte, Kontingente und Auto-Freigabe genau wie in der Weboberfläche; Wünsche
erscheinen unter dem eigenen Namen. Zuordnung: gleicher Name (Seerr-, Jellyfin-Name,
Anzeigename oder E-Mail, klein geschrieben) oder SEERR_USER_MAP („hub=seerr,…“).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_min_role
from app.models.service_key import ServiceKey
from app.models.user import User, ROLE_CHILD
from app.plugins.base import get_setting
from app.routers.notifications import service_key
from app.services.notify import notify

router = APIRouter(prefix="/api/media", tags=["media"])
logger = logging.getLogger("hermes.media")

MediaType = Literal["movie", "tv"]
POSTER = "https://image.tmdb.org/t/p/w342"
MIN_QUERY = 2

# Seerr: MediaStatus und MediaRequestStatus
MEDIA_STATUS = {2: "Angefragt", 3: "Wird geladen", 4: "Teilweise da", 5: "Verfügbar", 6: "Gesperrt"}
REQUEST_STATUS = {1: "Wartet auf Freigabe", 2: "Freigegeben", 3: "Abgelehnt", 4: "Fehlgeschlagen", 5: "Fertig"}


class SeerrError(Exception):
    pass


class NoAccount(Exception):
    pass


def _base() -> str:
    return str(get_setting("SEERR_URL") or "").rstrip("/")


def _active() -> bool:
    from app.plugins.registry import plugin_registry

    plugin = plugin_registry.get("seerr")
    return bool(plugin and plugin.active)


async def _seerr(method: str, path: str, *, as_user: Optional[int] = None, **kwargs) -> Any:
    headers = {"X-Api-Key": str(get_setting("SEERR_API_KEY") or ""), "Accept": "application/json"}
    if as_user is not None:
        headers["X-Api-User"] = str(as_user)
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            r = await client.request(method, f"{_base()}/api/v1{path}", headers=headers, **kwargs)
    except httpx.HTTPError as exc:
        raise SeerrError("Seerr nicht erreichbar") from exc
    try:
        data = r.json()
    except ValueError:
        data = {}
    if r.status_code >= 400:
        message = data.get("message") if isinstance(data, dict) else None
        raise SeerrError(message or f"Seerr antwortet {r.status_code}")
    return data


# ── Nutzer-Zuordnung ──────────────────────────────────────────────────────

_users_cache: Dict[str, Any] = {"at": 0.0, "base": None, "users": []}
USERS_TTL = 300


async def _seerr_users() -> List[dict]:
    if _users_cache["base"] == _base() and time.monotonic() - _users_cache["at"] < USERS_TTL:
        return _users_cache["users"]
    data = await _seerr("GET", "/user", params={"take": 500})
    users = [u for u in data.get("results", []) if isinstance(u, dict) and isinstance(u.get("id"), int)]
    _users_cache.update(at=time.monotonic(), base=_base(), users=users)
    return users


def _names(u: dict) -> set:
    out = set()
    for key in ("username", "jellyfinUsername", "displayName", "email"):
        value = u.get(key)
        if isinstance(value, str) and value.strip():
            out.add(value.strip().lower())
    return out


def _wanted_name(user: User) -> str:
    for pair in str(get_setting("SEERR_USER_MAP") or "").split(","):
        if "=" in pair:
            hub, seerr = pair.split("=", 1)
            if hub.strip().lower() == user.username.lower():
                return seerr.strip().lower()
    return user.username.lower()


async def _seerr_id(user: User) -> int:
    wanted = _wanted_name(user)
    matches = [u["id"] for u in await _seerr_users() if wanted in _names(u)]
    if len(matches) != 1:  # keiner oder mehrdeutig → lieber nichts in fremdem Namen
        raise NoAccount()
    return matches[0]


def _empty(status: str, error: Optional[str] = None) -> Dict[str, Any]:
    return {"status": status, "error": error, "items": []}


async def _guarded(user: User, run):
    if not _active():
        return _empty("not_configured")
    try:
        seerr_id = await _seerr_id(user)
        return {"status": "ok", "error": None, "items": await run(seerr_id)}
    except NoAccount:
        return _empty("no_account", "Kein passender Seerr-Nutzer – Admin: Zuordnung in den Plugin-Einstellungen")
    except SeerrError as exc:
        return _empty("unavailable", str(exc))


# ── Anzeige ───────────────────────────────────────────────────────────────


def _year(value: Any) -> Optional[int]:
    return int(value[:4]) if isinstance(value, str) and value[:4].isdigit() else None


def _item(r: dict) -> Dict[str, Any]:
    kind = r.get("mediaType")
    info = r.get("mediaInfo") or {}
    status = info.get("status") if isinstance(info, dict) else None
    poster = r.get("posterPath")
    return {
        "tmdb_id": r.get("id"),
        "media_type": kind,
        "title": r.get("title") if kind == "movie" else r.get("name"),
        "year": _year(r.get("releaseDate") if kind == "movie" else r.get("firstAirDate")),
        "overview": (r.get("overview") or "")[:400],
        "poster": f"{POSTER}{poster}" if isinstance(poster, str) and poster.startswith("/") else None,
        "status": status if status in MEDIA_STATUS else None,
        "status_label": MEDIA_STATUS.get(status),
        # 4 = teilweise da: weitere Staffeln wünschbar; 7 = gelöscht: neu wünschbar
        "requestable": status not in (2, 3, 5, 6),
    }


_meta_cache: Dict[tuple, tuple] = {}
META_TTL = 24 * 3600


async def _meta(kind: str, tmdb_id: int, seerr_id: int) -> dict:
    key = (_base(), kind, tmdb_id)
    hit = _meta_cache.get(key)
    if hit and time.monotonic() - hit[0] < META_TTL:
        return hit[1]
    try:
        data = await _seerr("GET", f"/{kind}/{tmdb_id}", as_user=seerr_id, params={"language": "de"})
    except SeerrError:
        return {}
    meta = {"title": data.get("title") if kind == "movie" else data.get("name"),
            "year": _year(data.get("releaseDate") if kind == "movie" else data.get("firstAirDate")),
            "poster": f"{POSTER}{data['posterPath']}" if isinstance(data.get("posterPath"), str) else None}
    if len(_meta_cache) > 1000:
        _meta_cache.clear()
    _meta_cache[key] = (time.monotonic(), meta)
    return meta


# ── Endpunkte ─────────────────────────────────────────────────────────────


@router.get("/search")
async def search(q: str, user: User = Depends(get_current_user)):
    """Filme und Serien suchen (deutsche Titel). Die App sucht nur auf Enter."""
    query = " ".join(q.split())
    if len(query) < MIN_QUERY:
        return await _guarded(user, lambda _: _noop())

    async def run(seerr_id: int):
        # Seerr verlangt %20 statt + in der Suche
        data = await _seerr("GET", f"/search?query={quote(query, safe='')}&page=1&language=de", as_user=seerr_id)
        return [_item(r) for r in data.get("results", []) if r.get("mediaType") in ("movie", "tv")]

    return await _guarded(user, run)


async def _noop():
    return []


@router.get("/requests")
async def my_requests(user: User = Depends(get_current_user)):
    """Eigene Wünsche, neueste zuerst."""

    async def run(seerr_id: int):
        data = await _seerr("GET", "/request", as_user=seerr_id,
                            params={"take": 50, "skip": 0, "filter": "all", "sort": "added", "requestedBy": seerr_id})
        mine = [r for r in data.get("results", [])
                if isinstance(r, dict) and (r.get("requestedBy") or {}).get("id") == seerr_id]
        metas = await asyncio.gather(*(
            _meta(r.get("type") or (r.get("media") or {}).get("mediaType"), (r.get("media") or {}).get("tmdbId"), seerr_id)
            for r in mine))
        out = []
        for r, meta in zip(mine, metas):
            media = r.get("media") or {}
            status = r.get("status")
            media_status = media.get("status")
            label = MEDIA_STATUS.get(media_status) if status in (2, 5) and media_status in (3, 4, 5) else None
            out.append({
                "id": r.get("id"),
                "media_type": r.get("type") or media.get("mediaType"),
                "tmdb_id": media.get("tmdbId"),
                "title": meta.get("title") or "Unbekannter Titel",
                "year": meta.get("year"),
                "poster": meta.get("poster"),
                "status": status,
                "status_label": label or REQUEST_STATUS.get(status, "Unbekannt"),
                "available": media_status == 5,
                "can_cancel": status == 1,
                "created_at": r.get("createdAt"),
            })
        return out

    return await _guarded(user, run)


class MediaRequestIn(BaseModel):
    media_type: MediaType
    tmdb_id: int = Field(gt=0)


@router.post("/requests", status_code=201)
async def create_request(data: MediaRequestIn, user: User = Depends(require_min_role(ROLE_CHILD))):
    if not _active():
        raise HTTPException(503, "Seerr ist nicht eingerichtet")
    try:
        seerr_id = await _seerr_id(user)
    except NoAccount:
        raise HTTPException(403, "Kein passender Seerr-Nutzer")
    except SeerrError as exc:
        raise HTTPException(503, str(exc))
    body: Dict[str, Any] = {"mediaType": data.media_type, "mediaId": data.tmdb_id}
    if data.media_type == "tv":
        body["seasons"] = "all"
    try:
        created = await _seerr("POST", "/request", as_user=seerr_id, json=body)
    except SeerrError as exc:
        # z. B. „schon angefragt“ oder Kontingent erreicht → lesbar weitergeben
        raise HTTPException(422, str(exc)) from exc
    status = created.get("status") if isinstance(created, dict) else None
    return {"id": created.get("id") if isinstance(created, dict) else None, "status": status,
            "status_label": REQUEST_STATUS.get(status, "Gewünscht")}


@router.delete("/requests/{request_id}")
async def cancel_request(request_id: int, user: User = Depends(require_min_role(ROLE_CHILD))):
    """Eigenen, noch nicht freigegebenen Wunsch zurückziehen. Fremde → 404."""
    if not _active():
        raise HTTPException(503, "Seerr ist nicht eingerichtet")
    try:
        seerr_id = await _seerr_id(user)
        existing = await _seerr("GET", f"/request/{request_id}", as_user=seerr_id)
    except (NoAccount, SeerrError):
        raise HTTPException(404, "Wunsch nicht gefunden")
    if (existing.get("requestedBy") or {}).get("id") != seerr_id:
        raise HTTPException(404, "Wunsch nicht gefunden")
    if existing.get("status") != 1:
        raise HTTPException(409, "Schon bearbeitet – zurückziehen geht nur, solange er auf Freigabe wartet")
    try:
        await _seerr("DELETE", f"/request/{request_id}", as_user=seerr_id)
    except SeerrError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"deleted": True}


# ── Webhook von Seerr ─────────────────────────────────────────────────────


@router.post("/webhook")
async def seerr_webhook(payload: Dict[str, Any], key: ServiceKey = Depends(service_key),
                        db: Session = Depends(get_db)):
    """Eingang für Seerrs Webhook-Benachrichtigung (Authorization-Header = Dienst-Schlüssel).

    Verfügbar/abgelehnt → an den, der gewünscht hat. Fehlgeschlagen → ihm und den Admins. Test → Admins.
    """
    event = str(payload.get("notification_type") or "")
    subject = str(payload.get("subject") or "Film/Serie")[:200]
    request = payload.get("request") or {}
    active = db.query(User).filter(User.is_active == True).all()  # noqa: E712
    admins = [u for u in active if u.is_admin]
    requester = None
    who = {str(request.get(k) or "").strip().lower() for k in ("requestedBy_username", "requestedBy_email")} - {""}
    if who and _active():
        try:
            seerr_ids = {u["id"] for u in await _seerr_users() if _names(u) & who}
            for u in active:
                try:
                    if await _seerr_id(u) in seerr_ids:
                        requester = u
                        break
                except NoAccount:
                    continue
        except SeerrError:
            logger.warning("Seerr-Webhook: Nutzerliste nicht abrufbar")

    if event == "TEST_NOTIFICATION":
        recipients, head, body = admins, "🎬 Seerr ist verbunden", str(payload.get("message") or "")
    elif event == "MEDIA_AVAILABLE":
        recipients, head, body = ([requester] if requester else []), f"🎬 „{subject}“ ist da", "Jetzt in Jellyfin."
    elif event == "MEDIA_DECLINED":
        recipients, head, body = ([requester] if requester else []), f"🎬 „{subject}“ abgelehnt", str(payload.get("message") or "")
    elif event == "MEDIA_FAILED":
        recipients = ([requester] if requester else []) + admins
        head, body = f"🎬 „{subject}“ hat nicht geklappt", str(payload.get("message") or "")
    else:
        return {"ignored": event or "unknown"}

    unique = list({u.id: u for u in recipients}.values())
    for u in unique:
        await notify(u.id, head, body[:500], data={"route": "/media"}, category="media", source=key.name)
    return {"recipients": [u.username for u in unique]}
