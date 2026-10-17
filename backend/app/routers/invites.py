"""Einladungen (#B): Admin lädt ein, die Person setzt mit dem Code ihr eigenes Passwort.

- ``POST /api/admin/invites``: Person (Name, E-Mail, Rolle) anlegen und Code erzeugen (7 Tage, einmalig).
- ``GET /api/admin/invites``: offene Einladungen (ohne Codes).
- ``POST /api/admin/invites/{id}/renew``: neuer Code, der alte wird ungültig.
- ``DELETE /api/admin/invites/{id}``: zurückziehen; hat sich die Person nie angemeldet, wird ihr Konto deaktiviert.
- ``POST /api/invites/accept`` (öffentlich): Code + Passwort → angemeldet. Begrenzte Fehlversuche.

Mit Anmeldedienst (OIDC) meldet sich die Person einfach mit derselben E-Mail an; Name und Rolle stehen dann fest.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.config import settings
from app.core.database import get_db
from app.core.security import (check_rate_limit, create_access_token, create_refresh_token, get_password_hash,
                               log_login_attempt, require_min_role, set_auth_cookies)
from app.models.invite import Invite
from app.models.user import ROLE_ADMIN, VALID_ROLES, User

router = APIRouter(tags=["invites"])
admin_only = require_min_role(ROLE_ADMIN)

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
VALID_DAYS = 7


def _new_code() -> str:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(12))
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"


def _normalize(code: str) -> str:
    raw = "".join(ch for ch in (code or "").upper() if ch in ALPHABET)
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}" if len(raw) == 12 else ""


def _view(inv: Invite, user: User) -> dict:
    return {
        "id": inv.id, "user_id": user.id, "display_name": user.effective_name, "email": user.email,
        "username": user.username, "role": user.role, "created_at": inv.created_at.isoformat(),
        "expires_at": inv.expires_at.isoformat(), "expired": inv.expires_at < datetime.utcnow(),
    }


def _issue(db: Session, user: User, admin: User) -> tuple[Invite, str]:
    code = _new_code()
    inv = Invite(user_id=user.id, code_hash=Invite.hash(code), created_by=admin.id,
                 expires_at=datetime.utcnow() + timedelta(days=VALID_DAYS))
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv, code


class InviteIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=40)
    email: str = Field(min_length=3, max_length=200)
    role: str = "partner"

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
            raise ValueError("Ungültige E-Mail-Adresse")
        return v

    @field_validator("role")
    @classmethod
    def _role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError("Unbekannte Rolle")
        return v


def _username_for(db: Session, email: str) -> str:
    base = re.sub(r"[^a-z0-9._-]", "", email.split("@")[0].lower())[:30] or "person"
    name, n = base, 1
    while db.query(User).filter(User.username == name).first():
        n += 1
        name = f"{base}{n}"
    return name


@router.post("/api/admin/invites", status_code=201)
async def create_invite(data: InviteIn, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    if db.query(User).filter(User.email.ilike(data.email)).first():
        raise HTTPException(409, "Diese E-Mail-Adresse gehört schon zu einer Person im Hub")
    user = User(username=_username_for(db, data.email), email=data.email, full_name=data.display_name.strip(),
                hashed_password=get_password_hash(secrets.token_urlsafe(32)),  # unbenutzbar bis zur Einlösung
                role=data.role, is_admin=data.role == ROLE_ADMIN, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    inv, code = _issue(db, user, admin)
    return {**_view(inv, user), "code": code, "oidc": bool(settings.oidc_issuer and settings.oidc_client_id)}


@router.get("/api/admin/invites")
async def list_invites(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    rows = (db.query(Invite, User).join(User, User.id == Invite.user_id)
            .filter(Invite.used_at.is_(None), Invite.revoked_at.is_(None)).order_by(Invite.created_at.desc()).all())
    return {"items": [_view(i, u) for i, u in rows]}


def _open_invite(db: Session, invite_id: int) -> tuple[Invite, User]:
    row = (db.query(Invite, User).join(User, User.id == Invite.user_id)
           .filter(Invite.id == invite_id, Invite.used_at.is_(None), Invite.revoked_at.is_(None)).first())
    if not row:
        raise HTTPException(404, "Einladung nicht gefunden oder schon eingelöst")
    return row


@router.post("/api/admin/invites/{invite_id}/renew")
async def renew_invite(invite_id: int, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    old, user = _open_invite(db, invite_id)
    old.revoked_at = datetime.utcnow()
    db.commit()
    inv, code = _issue(db, user, admin)
    return {**_view(inv, user), "code": code, "oidc": bool(settings.oidc_issuer and settings.oidc_client_id)}


@router.delete("/api/admin/invites/{invite_id}")
async def revoke_invite(invite_id: int, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    inv, user = _open_invite(db, invite_id)
    inv.revoked_at = datetime.utcnow()
    if user.last_login is None:
        user.is_active = False  # nie angemeldet: Konto ruht, bis man es wieder freischaltet
    db.commit()
    return {"revoked": True, "deactivated": not user.is_active}


class AcceptIn(BaseModel):
    code: str = Field(min_length=12, max_length=20)
    password: str = Field(min_length=10, max_length=200)
    client: str = "web"


@router.post("/api/invites/accept")
async def accept_invite(data: AcceptIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """Öffentlich: Einladungscode einlösen, eigenes Passwort setzen, angemeldet sein."""
    ip = request.client.host if request.client else "unknown"
    if not check_rate_limit("einladung", ip, db):
        raise HTTPException(429, "Zu viele Versuche, bitte kurz warten")
    code = _normalize(data.code)
    inv = db.query(Invite).filter(Invite.code_hash == Invite.hash(code)).first() if code else None
    now = datetime.utcnow()
    if not inv or inv.used_at or inv.revoked_at or inv.expires_at < now:
        log_login_attempt("einladung", ip, success=False, db=db)
        raise HTTPException(403, "Einladungscode ungültig oder abgelaufen – bitte um einen neuen")
    user = db.get(User, inv.user_id)
    if not user or not user.is_active:
        raise HTTPException(403, "Dieses Konto ist deaktiviert")
    user.hashed_password = get_password_hash(data.password)
    user.last_login = now
    inv.used_at = now
    db.commit()
    log_login_attempt("einladung", ip, success=True, db=db)
    access = create_access_token(data={"sub": user.username})
    refresh = create_refresh_token(user.id, db, request)
    set_auth_cookies(response, access, refresh)
    return {
        "access_token": access, "token_type": "bearer",
        "refresh_token": refresh if data.client == "app" else None,
        "user": {"id": user.id, "username": user.username, "email": user.email, "full_name": user.full_name,
                 "role": user.role, "is_admin": user.is_admin},
    }
