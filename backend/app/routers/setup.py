"""Ersteinrichtung (#4): Status ohne Anmeldung, erstes Admin-Konto mit Einrichtungscode."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app import __version__
from app.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, create_refresh_token, get_password_hash, set_auth_cookies
from app.models.user import ROLE_ADMIN, User
from app.services import setup

router = APIRouter(prefix="/api/setup", tags=["setup"])


@router.get("/status")
async def status(db: Session = Depends(get_db)):
    """Öffentlich: Muss der Hub noch eingerichtet werden? Verrät keine Nutzerdaten."""
    return {
        "needs_setup": setup.needs_setup(db),
        "version": __version__,
        "app_name": settings.app_name,
        "oidc": bool(settings.oidc_issuer and settings.oidc_client_id),
        "code_required": setup.code_required(),
    }


class FirstAdmin(BaseModel):
    code: str | None = Field(default=None, max_length=20)
    username: str = Field(min_length=2, max_length=40)
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=10, max_length=200)
    display_name: str | None = Field(default=None, max_length=40)
    client: str = "web"

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.fullmatch(r"[a-z0-9._-]{2,40}", v):
            raise ValueError("Benutzername: klein, ohne Leerzeichen (a–z, 0–9, . _ -)")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip()
        if "@" not in v or v.startswith("@") or v.endswith("@"):
            raise ValueError("Ungültige E-Mail-Adresse")
        return v


@router.post("/admin", status_code=201)
async def first_admin(data: FirstAdmin, request: Request, response: Response, db: Session = Depends(get_db)):
    """Legt das erste Admin-Konto an und meldet es an. Nur solange es keinen aktiven Admin gibt."""
    if not setup.needs_setup(db):
        raise HTTPException(409, "Der Hub ist bereits eingerichtet")
    if not setup.check_code(data.code):
        raise HTTPException(403, "Einrichtungscode stimmt nicht (steht im Server-Log)")
    if db.query(User).filter((User.username == data.username) | (User.email == data.email)).first():
        raise HTTPException(409, "Benutzername oder E-Mail gibt es schon")
    user = User(username=data.username, email=data.email, hashed_password=get_password_hash(data.password),
                full_name=(data.display_name or "").strip() or data.username, role=ROLE_ADMIN, is_admin=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    setup.finish()
    access = create_access_token(data={"sub": user.username})
    refresh = create_refresh_token(user.id, db, request)
    set_auth_cookies(response, access, refresh)
    return {
        "access_token": access,
        "token_type": "bearer",
        "refresh_token": refresh if data.client == "app" else None,
        "user": {"id": user.id, "username": user.username, "email": user.email, "full_name": user.full_name,
                 "role": user.role, "is_admin": True},
    }
