"""Benachrichtigungs-Zentrale.

- ``POST /api/notify``: Eingang für andere Systeme (Home Assistant, Shelfarr, Paperless …),
  nur mit Dienst-Schlüssel (``fhs_…``). Ruhezeiten/Kategorien der Empfänger gelten.
- ``/api/me/notifications``: Verlauf der eigenen Mitteilungen.
- ``/api/admin/service-keys``: Dienst-Schlüssel verwalten (nur Admin).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_min_role
from app.models.notification_log import NotificationLog
from app.models.service_key import SERVICE_KEY_PREFIX, ServiceKey
from app.models.user import ROLE_ADMIN, User
from app.services.notify import CATEGORIES, notify

router = APIRouter(tags=["notifications"])


# ── Eingang ────────────────────────────────────────────────────────────────


def service_key(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)) -> ServiceKey:
    raw = (authorization or "").removeprefix("Bearer ").strip()
    if not raw.startswith(SERVICE_KEY_PREFIX):
        raise HTTPException(status_code=401, detail="Dienst-Schlüssel erforderlich")
    key = db.query(ServiceKey).filter(ServiceKey.key_hash == ServiceKey.hash(raw), ServiceKey.revoked_at.is_(None)).first()
    if not key:
        raise HTTPException(status_code=401, detail="Dienst-Schlüssel ungültig")
    key.last_used_at = datetime.utcnow()
    db.commit()
    return key


class NotifyIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field("", max_length=2000)
    to: Union[str, List[str]] = "family"  # "family" | "admins" | Benutzername(n)
    category: str = "system"
    route: Optional[str] = None  # Ziel in der App, z. B. /shopping
    data: Dict[str, Any] = {}
    silent: bool = False  # nur in den Verlauf, kein Push (Quelle pusht selbst)


def _recipients(db: Session, to: Union[str, List[str]]) -> List[User]:
    active = db.query(User).filter(User.is_active == True)  # noqa: E712
    names = [to] if isinstance(to, str) else list(to)
    lowered = [n.strip().lower() for n in names if n.strip()]
    if lowered == ["family"] or lowered == ["familie"]:
        return active.order_by(User.id).all()
    if lowered == ["admins"]:
        return active.filter(User.is_admin == True).order_by(User.id).all()  # noqa: E712
    users = {u.username.lower(): u for u in active.all()}
    unknown = [n for n in lowered if n not in users]
    if unknown:
        raise HTTPException(status_code=422, detail={"error": "unknown_recipient", "names": unknown})
    return [users[n] for n in dict.fromkeys(lowered)]


@router.post("/api/notify")
async def notify_in(data: NotifyIn, key: ServiceKey = Depends(service_key), db: Session = Depends(get_db)):
    if data.category not in CATEGORIES:
        raise HTTPException(status_code=422, detail={"error": "unknown_category", "allowed": list(CATEGORIES)})
    users = _recipients(db, data.to)
    payload = {k: str(v) for k, v in data.data.items()}
    if data.route:
        payload["route"] = data.route
    delivered = 0
    for u in users:
        delivered += await notify(u.id, data.title, data.body, data=payload, category=data.category,
                                  source=key.name, silent=data.silent)
    return {"recipients": [u.username for u in users], "delivered": delivered}


# ── Verlauf ────────────────────────────────────────────────────────────────


def _entry(n: NotificationLog) -> Dict[str, Any]:
    return {
        "id": n.id, "title": n.title, "body": n.body, "category": n.category, "route": n.route,
        "source": n.source, "created_at": n.created_at.isoformat() + "Z", "read": n.read_at is not None,
        "pushed": not n.suppressed,
    }


@router.get("/api/me/notifications")
async def my_notifications(limit: int = 50, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(NotificationLog).filter(NotificationLog.user_id == user.id)
    unread = q.filter(NotificationLog.read_at.is_(None)).count()
    items = q.order_by(NotificationLog.created_at.desc(), NotificationLog.id.desc()).limit(max(1, min(limit, 200))).all()
    return {"unread": unread, "items": [_entry(n) for n in items]}


class MarkRead(BaseModel):
    ids: Optional[List[int]] = None  # leer = alle


@router.post("/api/me/notifications/read")
async def mark_read(data: MarkRead, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(NotificationLog).filter(NotificationLog.user_id == user.id, NotificationLog.read_at.is_(None))
    if data.ids:
        q = q.filter(NotificationLog.id.in_(data.ids))
    count = q.update({NotificationLog.read_at: datetime.utcnow()}, synchronize_session=False)
    db.commit()
    return {"marked": count}


# ── Dienst-Schlüssel (Admin) ───────────────────────────────────────────────


class ServiceKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)


def _key(k: ServiceKey) -> Dict[str, Any]:
    return {"id": k.id, "name": k.name, "hint": k.hint, "created_at": k.created_at.isoformat(),
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None}


@router.get("/api/admin/service-keys")
async def list_keys(db: Session = Depends(get_db), _: User = Depends(require_min_role(ROLE_ADMIN))):
    keys = db.query(ServiceKey).filter(ServiceKey.revoked_at.is_(None)).order_by(ServiceKey.created_at.desc()).all()
    return [_key(k) for k in keys]


@router.post("/api/admin/service-keys", status_code=status.HTTP_201_CREATED)
async def create_key(data: ServiceKeyCreate, db: Session = Depends(get_db), _: User = Depends(require_min_role(ROLE_ADMIN))):
    raw = ServiceKey.generate()
    key = ServiceKey(name=data.name.strip(), key_hash=ServiceKey.hash(raw), hint=raw[:8])
    db.add(key)
    db.commit()
    db.refresh(key)
    return {**_key(key), "key": raw}


@router.delete("/api/admin/service-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_key(key_id: int, db: Session = Depends(get_db), _: User = Depends(require_min_role(ROLE_ADMIN))):
    key = db.query(ServiceKey).filter(ServiceKey.id == key_id, ServiceKey.revoked_at.is_(None)).first()
    if not key:
        raise HTTPException(status_code=404, detail="Schlüssel nicht gefunden")
    key.revoked_at = datetime.utcnow()
    db.commit()


# ── Aktualisieren auf Zuruf (z. B. Home Assistant: Einkaufsliste per Sprache geändert) ──


class RefreshIn(BaseModel):
    scope: str = "external"


@router.post("/api/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh_devices(data: RefreshIn, key: ServiceKey = Depends(service_key)):
    """Geräte laden neu und aktualisieren ihre Widgets (stille Push-Nachricht, gebündelt)."""
    from app.services import refresh

    if data.scope not in refresh.SCOPES:
        raise HTTPException(status_code=422, detail={"error": "unknown_scope", "allowed": list(refresh.SCOPES)})
    refresh.schedule_refresh(data.scope)
    return {"scheduled": data.scope}
