"""Paperless-ngx (#30): Suche, neueste Dokumente, Vorschaubilder, Fristen.

Jede Person hinterlegt ihr eigenes Paperless-API-Token; der Hub sieht damit genau, was die Person in
Paperless sieht (kein Admin-Token). Fristen liegen als benutzerdefinierte Felder „Frist“ (Datum) und
„Aufgabe“ (Text) am Dokument (setzt das KI-Skript beim Einlesen).
"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.crypto import decrypt, encrypt
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.timeutil import local_tz, to_utc_naive
from app.models.paperless import PaperlessAccount
from app.models.reminder import Reminder
from app.models.user import User
from app.plugins.base import get_setting

router = APIRouter(prefix="/api/paperless", tags=["paperless"])


class AuthFailed(Exception):
    pass


class Unavailable(Exception):
    pass


def _base() -> str:
    return str(get_setting("PAPERLESS_URL") or "").rstrip("/")


def _public() -> str:
    return str(get_setting("PAPERLESS_PUBLIC_URL") or "").rstrip("/") or _base()


def _active() -> bool:
    from app.plugins.registry import plugin_registry

    plugin = plugin_registry.get("paperless")
    return bool(plugin and plugin.active)


async def _call(token: str, path: str, params: Optional[dict] = None, raw: bool = False):
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            r = await client.get(f"{_base()}{path}", params=params,
                                 headers={"Authorization": f"Token {token}", "Accept": "application/json; version=9"})
    except httpx.HTTPError as exc:
        raise Unavailable(f"Paperless nicht erreichbar: {exc}") from exc
    if r.status_code in (401, 403):
        raise AuthFailed()
    if r.status_code != 200:
        raise Unavailable(f"Paperless antwortet {r.status_code}")
    return r if raw else r.json()


def _empty(status_: str, error: Optional[str] = None) -> Dict[str, Any]:
    return {"status": status_, "error": error, "items": []}


def _token(db: Session, user: User) -> Optional[str]:
    acc = db.get(PaperlessAccount, user.id)
    return decrypt(acc.token_enc) if acc else None


async def _names(token: str, path: str) -> Dict[int, str]:
    data = await _call(token, path, {"page_size": 1000, "fields": "id,name"})
    return {int(x["id"]): x["name"] for x in data.get("results", [])}


async def _items(token: str, docs: List[dict]) -> List[Dict[str, Any]]:
    corr = await _names(token, "/api/correspondents/")
    types = await _names(token, "/api/document_types/")
    tags = await _names(token, "/api/tags/")
    return [{
        "id": d["id"],
        "title": d.get("title") or "",
        "created": (d.get("created") or "")[:10],
        "correspondent": corr.get(d.get("correspondent")),
        "document_type": types.get(d.get("document_type")),
        "tags": [tags[t] for t in d.get("tags") or [] if t in tags],
        "url": f"{_public()}/documents/{d['id']}/details",
        "thumb": f"/api/paperless/documents/{d['id']}/thumb",
    } for d in docs]


async def _guarded(db: Session, user: User, run):
    if not _active():
        return _empty("not_configured")
    token = _token(db, user)
    if token is None:
        return _empty("no_account")
    try:
        return {"status": "ok", "error": None, "items": await run(token)}
    except AuthFailed:
        return _empty("auth_failed", "Paperless-Zugang ungültig – Token in der App neu eintragen")
    except Unavailable as exc:
        return _empty("unavailable", str(exc))


FIELDS = "id,title,created,correspondent,document_type,tags,custom_fields"


# ── Zugang ────────────────────────────────────────────────────────────────


class AccountIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)


@router.get("/account")
async def get_account(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    acc = db.get(PaperlessAccount, user.id)
    return {"configured": _active(), "connected": acc is not None, "username": acc.remote_username if acc else None}


@router.put("/account")
async def put_account(data: AccountIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not _active():
        raise HTTPException(409, "Paperless ist nicht eingerichtet")
    token = data.token.strip()
    try:
        info = await _call(token, "/api/ui_settings/")
    except AuthFailed:
        raise HTTPException(422, "Paperless kennt dieses Token nicht")
    except Unavailable as exc:
        raise HTTPException(503, str(exc))
    remote = ((info or {}).get("user") or {}).get("username")
    acc = db.get(PaperlessAccount, user.id) or PaperlessAccount(user_id=user.id)
    acc.token_enc, acc.remote_username, acc.verified_at = encrypt(token), remote, datetime.utcnow()
    db.add(acc)
    db.commit()
    return {"connected": True, "username": remote}


@router.delete("/account")
async def delete_account(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    acc = db.get(PaperlessAccount, user.id)
    if acc:
        db.delete(acc)
        db.commit()
    return {"connected": False}


# ── Dokumente ─────────────────────────────────────────────────────────────


@router.get("/recent")
async def recent(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    async def run(token):
        data = await _call(token, "/api/documents/", {"ordering": "-added", "page_size": 20, "fields": FIELDS})
        return await _items(token, data.get("results", []))
    return await _guarded(db, user, run)


@router.get("/search")
async def search(q: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if len(q.strip()) < 2:
        return _empty("ok")

    async def run(token):
        data = await _call(token, "/api/documents/", {"query": q.strip(), "page_size": 30, "fields": FIELDS})
        return await _items(token, data.get("results", []))
    return await _guarded(db, user, run)


@router.get("/documents/{doc_id}/thumb")
async def thumb(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    token = _token(db, user)
    if token is None or not _active():
        raise HTTPException(404, "Kein Paperless-Zugang")
    try:
        r = await _call(token, f"/api/documents/{doc_id}/thumb/", raw=True)
    except AuthFailed:
        raise HTTPException(403, "Paperless-Zugang ungültig")
    except Unavailable:
        raise HTTPException(502, "Vorschau nicht verfügbar")
    mime = r.headers.get("content-type", "").split(";")[0].strip()
    if mime not in ("image/webp", "image/png", "image/jpeg"):
        raise HTTPException(502, "Vorschau ist kein Bild")
    return Response(content=r.content, media_type=mime, headers={
        "Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'"})


# ── Fristen ───────────────────────────────────────────────────────────────


async def _deadlines(token: str) -> List[Dict[str, Any]]:
    fields = {f["name"]: f["id"] for f in (await _call(token, "/api/custom_fields/", {"page_size": 100})).get("results", [])}
    if "Frist" not in fields:
        return []
    data = await _call(token, "/api/documents/", {
        "custom_field_query": json.dumps(["Frist", "gte", date.today().isoformat()]),
        "page_size": 50, "fields": FIELDS})
    docs = data.get("results", [])
    items = await _items(token, docs)
    out = []
    for doc, item in zip(docs, items):
        values = {cf.get("field"): cf.get("value") for cf in doc.get("custom_fields") or []}
        deadline = values.get(fields["Frist"])
        if not deadline:
            continue
        out.append({**item, "deadline": deadline, "task": values.get(fields.get("Aufgabe")) or item["title"]})
    return sorted(out, key=lambda x: x["deadline"])


@router.get("/deadlines")
async def deadlines(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return await _guarded(db, user, _deadlines)


@router.post("/deadlines/{doc_id}/remind")
async def remind(doc_id: int, response: Response, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Frist eines Dokuments als eigene Erinnerung (am Fristtag 9 Uhr). Zweimal → kein Duplikat."""
    result = await _guarded(db, user, _deadlines)
    if result["status"] != "ok":
        raise HTTPException(409, result.get("error") or "Paperless nicht verfügbar")
    item = next((d for d in result["items"] if d["id"] == doc_id), None)
    if item is None:
        raise HTTPException(404, "Keine anstehende Frist für dieses Dokument")
    source = f"paperless:{doc_id}"
    existing = db.query(Reminder).filter(Reminder.created_by == user.id, Reminder.source == source,
                                         Reminder.completed == False).first()  # noqa: E712
    if existing:
        return {"id": existing.id, "created": False}
    due = datetime.combine(date.fromisoformat(item["deadline"]), time(9, 0)).replace(tzinfo=local_tz())
    reminder = Reminder(title=f"📄 {item['task']}", notes=f"{item['title']}\n{item['url']}", due_at=to_utc_naive(due),
                        source=source, created_by=user.id, for_family=False)
    db.add(reminder)
    db.commit()
    response.status_code = status.HTTP_201_CREATED
    return {"id": reminder.id, "created": True}
