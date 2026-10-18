"""Bücher und Hörbücher wünschen über Shelfarr.

Der Hub spricht mit einem Shelfarr-Token (Admin-Nutzer, Scopes search:read, requests:read,
requests:write) und legt Wünsche im Namen des passenden Shelfarr-Nutzers an. Zuordnung:
gleicher Benutzername (klein geschrieben) oder SHELFARR_USER_MAP („hub=shelfarr,…“).
Sprache ist immer SHELFARR_LANGUAGE (Standard de).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Literal, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.core.database import get_db
from app.core.security import get_current_user, require_min_role
from app.models.service_key import ServiceKey
from app.models.user import User, ROLE_CHILD
from app.routers.notifications import service_key
from app.services.notify import notify

router = APIRouter(prefix="/api/books", tags=["books"])
logger = logging.getLogger("hermes.books")

BookType = Literal["ebook", "audiobook"]

# Shelfarr-Status → kurze deutsche Anzeige
STATUS_LABELS = {
    "pending": "Wartet",
    "searching": "Wird gesucht",
    "not_found": "Nicht gefunden",
    "downloading": "Lädt herunter",
    "processing": "Wird verarbeitet",
    "completed": "Fertig",
    "failed": "Fehlgeschlagen",
    "awaiting_purchase": "Nur zum Kauf",
}


# Kürzere Suchen gehen nicht an Shelfarr: OpenLibrary lehnt sie mit 422 ab, und Shelfarr sperrt
# die Quelle nach jedem Fehler minutenlang (danach liefert die Suche gar nichts mehr).
MIN_QUERY = 3

# Gleiche Suche kurz merken: jede Shelfarr-Suche fragt Google Books, und dessen Kontingent ist knapp.
SEARCH_TTL = 600
SEARCH_CACHE_MAX = 200
_search_cache: Dict[tuple, tuple] = {}


def _cached_search(key: tuple) -> Optional[list]:
    hit = _search_cache.get(key)
    if hit and time.monotonic() - hit[0] < SEARCH_TTL:
        return hit[1]
    _search_cache.pop(key, None)
    return None


def _remember_search(key: tuple, items: list) -> None:
    if len(_search_cache) >= SEARCH_CACHE_MAX:
        _search_cache.pop(next(iter(_search_cache)))  # ältesten Eintrag verwerfen
    _search_cache[key] = (time.monotonic(), items)


class BookRequestCreate(BaseModel):
    work_id: str
    book_type: BookType
    title: str
    author: Optional[str] = None
    cover_url: Optional[str] = None
    year: Optional[int] = None


class ShelfarrError(Exception):
    pass


def _configured() -> bool:
    return bool(settings.shelfarr_url and settings.shelfarr_token)


def shelfarr_username(user: User) -> str:
    mapping = {}
    for pair in (settings.shelfarr_user_map or "").split(","):
        if "=" in pair:
            hub, shelf = pair.split("=", 1)
            mapping[hub.strip().lower()] = shelf.strip().lower()
    return mapping.get(user.username.lower(), user.username.lower())


def hub_username(shelfarr_name: str) -> str:
    """Gegenrichtung zu shelfarr_username: Shelfarr-Name → Hub-Benutzername."""
    name = (shelfarr_name or "").strip().lower()
    for pair in (settings.shelfarr_user_map or "").split(","):
        if "=" in pair:
            hub, shelf = pair.split("=", 1)
            if shelf.strip().lower() == name:
                return hub.strip().lower()
    return name


async def _shelfarr(method: str, path: str, **kwargs) -> Dict[str, Any]:
    """Ein Aufruf an die Shelfarr-API. Fehler als ShelfarrError mit Klartext."""
    url = f"{settings.shelfarr_url.rstrip('/')}/api/v1{path}"
    headers = {"Authorization": f"Bearer {settings.shelfarr_token}", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.request(method, url, headers=headers, **kwargs)
    except httpx.HTTPError as exc:
        raise ShelfarrError(f"Shelfarr nicht erreichbar: {exc}") from exc
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.status_code >= 400:
        errors = data.get("errors") if isinstance(data, dict) else None
        raise ShelfarrError("; ".join(errors) if errors else f"Shelfarr antwortet {resp.status_code}")
    return data


def _unavailable(error: str, key: str) -> Dict[str, Any]:
    status = "unavailable" if _configured() else "not_configured"
    return {"status": status, "error": error, key: []}


def _request_item(r: Dict[str, Any]) -> Dict[str, Any]:
    book = r.get("book") or {}
    status = r.get("status")
    return {
        "id": r.get("id"),
        "status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "attention_needed": bool(r.get("attention_needed")),
        "issue": r.get("issue_description"),
        "title": book.get("title"),
        "author": book.get("author"),
        "book_type": book.get("book_type"),
        "created_at": r.get("created_at"),
    }


@router.get("/search")
async def search(q: str, book_type: Optional[BookType] = None, _: User = Depends(get_current_user)):
    """Suche in Shelfarrs Metadatenquellen. Liefert {status, error, items}.

    Die App sucht nur auf Enter und filtert E-Book/Hörbuch selbst; gleiche Suchen kommen aus dem Cache.
    """
    if not _configured():
        return _unavailable("Shelfarr ist nicht eingerichtet", "items")
    query = " ".join(q.split())
    if len(query) < MIN_QUERY:
        return {"status": "ok", "error": None, "items": []}
    key = (settings.shelfarr_url, query.lower())
    items = _cached_search(key)
    if items is None:
        try:
            data = await _shelfarr("GET", "/search", params={"q": query, "limit": 20})
        except ShelfarrError as exc:
            return _unavailable(str(exc), "items")  # Fehler nicht merken: nächster Versuch fragt neu
        items = _search_items(data)
        _remember_search(key, items)
    if book_type:
        items = [i for i in items if book_type in i["book_types"]]
    return {"status": "ok", "error": None, "items": items}


def _search_items(data: Dict[str, Any]) -> list:
    items = []
    for r in data.get("results", []):
        if r.get("content_kind") not in (None, "book"):
            continue  # Comics usw. nicht anbieten
        types = r.get("available_book_types") or ["ebook", "audiobook"]
        items.append({
            "work_id": r.get("work_id"),
            "title": r.get("title"),
            "author": r.get("author"),
            "year": r.get("year"),
            "cover_url": r.get("cover_url"),
            "series": r.get("series_name"),
            "series_position": r.get("series_position"),
            "book_types": [t for t in types if t in ("ebook", "audiobook")],
        })
    return items


@router.get("/discover")
async def discover(shelf: str = "popular", _: User = Depends(get_current_user)):
    """Browse books that exist in German (Open Library): popular, new, well rated, by genre. Request them as usual."""
    import httpx

    from app.services import book_discover

    if shelf not in book_discover.SHELVES:
        raise HTTPException(422, "Unbekanntes Regal")
    base = {"shelves": book_discover.SHELVES, "shelf": shelf}
    if not _configured():
        return {**_unavailable("Shelfarr ist nicht eingerichtet", "items"), **base}
    try:
        return {"status": "ok", "error": None, "items": await book_discover.shelf(shelf), **base}
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Open Library nicht erreichbar: %s", type(exc).__name__)
        return {"status": "unavailable", "error": "Open Library gerade nicht erreichbar", "items": [], **base}


@router.get("/requests")
async def my_requests(current_user: User = Depends(get_current_user)):
    """Eigene Wünsche, neueste zuerst."""
    if not _configured():
        return _unavailable("Shelfarr ist nicht eingerichtet", "items")
    try:
        data = await _shelfarr("GET", "/requests", params={"limit": 100})
    except ShelfarrError as exc:
        return _unavailable(str(exc), "items")
    me = shelfarr_username(current_user)
    mine = [r for r in data.get("requests", []) if (r.get("user") or {}).get("username", "").lower() == me]
    return {"status": "ok", "error": None, "items": [_request_item(r) for r in mine]}


@router.post("/requests", status_code=201)
async def create_request(data: BookRequestCreate, current_user: User = Depends(require_min_role(ROLE_CHILD))):
    if not _configured():
        raise HTTPException(503, "Shelfarr ist nicht eingerichtet")
    payload = {
        "username": shelfarr_username(current_user),
        "work_id": data.work_id,
        "book_type": data.book_type,
        "title": data.title,
        "author": data.author,
        "cover_url": data.cover_url,
        "year": data.year,
        "language": settings.shelfarr_language,
        "external_source": "familienhub",
    }
    try:
        created = await _shelfarr("POST", "/requests", json={k: v for k, v in payload.items() if v is not None})
    except ShelfarrError as exc:
        # z. B. „schon gewünscht“ oder unbekannte Ausgabe → für die App lesbar weitergeben
        raise HTTPException(422, str(exc)) from exc
    # Shelfarr: {requests: [...], queued, warnings, errors}; queued = wird im Hintergrund angelegt
    return {
        "items": [_request_item(r) for r in created.get("requests", [])],
        "queued": bool(created.get("queued")),
        "warnings": created.get("warnings") or [],
    }


@router.delete("/requests/{request_id}")
async def cancel_request(request_id: int, current_user: User = Depends(require_min_role(ROLE_CHILD))):
    """Eigenen Wunsch abbrechen. Fremde Wünsche → 404."""
    if not _configured():
        raise HTTPException(503, "Shelfarr ist nicht eingerichtet")
    try:
        existing = await _shelfarr("GET", f"/requests/{request_id}")
    except ShelfarrError:
        raise HTTPException(404, "Wunsch nicht gefunden")
    if (existing.get("user") or {}).get("username", "").lower() != shelfarr_username(current_user):
        raise HTTPException(404, "Wunsch nicht gefunden")
    try:
        cancelled = await _shelfarr("DELETE", f"/requests/{request_id}")
    except ShelfarrError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _request_item(cancelled)


# ── Webhook von Shelfarr ───────────────────────────────────────────────────

BOOK_TYPE_LABELS = {"audiobook": "Hörbuch", "ebook": "E-Book"}


@router.post("/webhook")
async def shelfarr_webhook(payload: Dict[str, Any], key: ServiceKey = Depends(service_key),
                           db: Session = Depends(get_db)):
    """Eingang für Shelfarrs Outbound-Webhook (Einstellungen → Webhook, Token = Dienst-Schlüssel).

    Fertig → nur an den, der gewünscht hat. Fehlgeschlagen/Eingriff nötig → an ihn und die Admins.
    „Angelegt“ wird ignoriert (hat man selbst ausgelöst). „test“ geht an die Admins.
    """
    event = str(payload.get("event") or "")
    book = payload.get("book") or {}
    title = book.get("title") or "Buch"
    active = db.query(User).filter(User.is_active == True)  # noqa: E712
    admins = active.filter(User.is_admin == True).order_by(User.id).all()  # noqa: E712
    wanted = hub_username((payload.get("user") or {}).get("username", ""))
    requester = next((u for u in active.all() if u.username.lower() == wanted), None) if wanted else None

    if event == "test":
        recipients, category = admins, "system"
        head, body = "📚 Shelfarr ist verbunden", str(payload.get("message") or "")
    elif event == "request_completed":
        recipients, category = [requester] if requester else admins, "media"
        kind = BOOK_TYPE_LABELS.get(book.get("book_type"), "Buch")
        author = f" von {book['author']}" if book.get("author") else ""
        head, body = f"📚 „{title}“ ist da", f"{kind}{author} liegt in der Bibliothek."
    elif event in ("request_failed", "request_attention"):
        recipients, category = ([requester] if requester else []) + admins, "media"
        verb = "hat nicht geklappt" if event == "request_failed" else "braucht Hilfe"
        head, body = f"📚 „{title}“ {verb}", str(payload.get("message") or "")
    else:
        return {"ignored": event or "unknown"}

    unique = list({u.id: u for u in recipients}.values())
    for u in unique:
        await notify(u.id, head, body, data={"route": "/books"}, category=category, source=key.name)
    return {"recipients": [u.username for u in unique]}
