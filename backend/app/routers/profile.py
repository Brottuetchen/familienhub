"""Eigenes Profil: Anzeigename, Avatar-Farbe, Profilbild.

Profilbilder sieht jede angemeldete Person der Familie (Avatare in Aufgaben, Kopf, Mitteilungen).
Erlaubt sind nur JPEG, PNG und WebP bis 512 KB; geprüft wird die Dateisignatur, nicht Endung oder
angegebener Typ. Ausgeliefert mit festem Bildtyp und nosniff, ohne Skripte (kein SVG).
"""

from __future__ import annotations

import base64
import binascii
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, UserAvatar

router = APIRouter(tags=["profile"])

MAX_AVATAR = 512 * 1024
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def sniff(data: bytes) -> Optional[str]:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def profile(u: User) -> dict:
    return {"id": u.id, "username": u.username, "email": u.email, "display_name": u.effective_name,
            "avatar_color": u.avatar_color, "avatar_url": u.avatar_url, "role": u.role}


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(None, max_length=40)
    avatar_color: Optional[str] = None

    @field_validator("avatar_color")
    @classmethod
    def _hex(cls, v):
        if v is not None and not HEX.match(v):
            raise ValueError("Farbe als #RRGGBB")
        return v.upper() if v else v


@router.get("/api/me/profile")
async def get_profile(user: User = Depends(get_current_user)):
    return profile(user)


@router.patch("/api/me/profile")
async def update_profile(data: ProfileUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    fields = data.model_fields_set
    if "display_name" in fields:
        user.display_name = (data.display_name or "").strip() or None
    if "avatar_color" in fields:
        user.avatar_color = data.avatar_color
    db.commit()
    db.refresh(user)
    return profile(user)


class AvatarUpload(BaseModel):
    image: str = Field(min_length=1)  # Base64 (ohne data:-Präfix)


@router.put("/api/me/avatar")
async def upload_avatar(body: AvatarUpload, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if len(body.image) > (MAX_AVATAR * 4) // 3 + 8:
        raise HTTPException(413, "Bild ist größer als 512 KB")
    try:
        data = base64.b64decode(body.image, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "Bilddaten ungültig")
    if len(data) > MAX_AVATAR:
        raise HTTPException(413, "Bild ist größer als 512 KB")
    mime = sniff(data)
    if mime is None:
        raise HTTPException(422, "Nur JPEG, PNG oder WebP")
    row = db.get(UserAvatar, user.id) or UserAvatar(user_id=user.id)
    row.content, row.mime, row.updated_at = data, mime, datetime.utcnow()
    db.add(row)
    user.has_avatar = True
    user.avatar_version = (user.avatar_version or 0) + 1
    db.commit()
    db.refresh(user)
    return profile(user)


@router.delete("/api/me/avatar")
async def delete_avatar(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.get(UserAvatar, user.id)
    if row:
        db.delete(row)
    user.has_avatar = False
    user.avatar_version = (user.avatar_version or 0) + 1  # alte URLs nie wiederverwenden
    db.commit()
    db.refresh(user)
    return profile(user)


@router.get("/api/users/{user_id}/avatar")
async def get_avatar(user_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    row = db.get(UserAvatar, user_id)
    if row is None:
        raise HTTPException(404, "Kein Profilbild")
    return Response(content=row.content, media_type=row.mime, headers={
        "Cache-Control": "private, max-age=604800",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'",
        "Content-Disposition": "inline",
    })
