"""Per-person ntfy settings (#23). The admin chooses the server; a person only chooses their topic."""

from __future__ import annotations

import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.ntfy import NtfyTarget
from app.models.user import User
from app.services.ntfy import ntfy_server

router = APIRouter(prefix="/api/me/ntfy", tags=["push"])

TOPIC_PATTERN = r"^[A-Za-z0-9_-]{12,64}$"


def new_topic() -> str:
    # 120 bits of randomness: the topic name is what keeps messages private on a shared server
    return "fh_" + secrets.token_urlsafe(15).replace("-", "x").replace("_", "y")


class NtfyIn(BaseModel):
    enabled: bool = True
    topic: Optional[str] = Field(default=None, pattern=TOPIC_PATTERN)


def _out(target: Optional[NtfyTarget]) -> dict:
    server = ntfy_server()
    topic = target.topic if target else None
    return {
        "available": server is not None,
        "server": server,
        "enabled": bool(target and target.enabled and server),
        "topic": topic,
        "subscribe_url": f"{server}/{topic}" if server and topic else None,
    }


@router.get("")
async def get_ntfy(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _out(db.get(NtfyTarget, user.id))


def _save_topic(db: Session, target: NtfyTarget, topic: str) -> None:
    taken = db.query(NtfyTarget).filter(NtfyTarget.topic == topic, NtfyTarget.user_id != target.user_id).first()
    if taken:
        raise HTTPException(status_code=409, detail="Dieses Topic ist schon vergeben")
    target.topic = topic


@router.put("")
async def put_ntfy(data: NtfyIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if ntfy_server() is None:
        raise HTTPException(status_code=409, detail="ntfy ist auf diesem Hub nicht eingerichtet")
    target = db.get(NtfyTarget, user.id)
    if target is None:
        target = NtfyTarget(user_id=user.id, topic=data.topic or new_topic(), enabled=data.enabled)
        _save_topic(db, target, target.topic)
        db.add(target)
    else:
        if data.topic:
            _save_topic(db, target, data.topic)
        target.enabled = data.enabled
    db.commit()
    return _out(target)


@router.post("/new-topic")
async def regenerate(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """New secret topic, e.g. when the old one was shared by accident. The phone must subscribe again."""
    target = db.get(NtfyTarget, user.id)
    if target is None or ntfy_server() is None:
        raise HTTPException(status_code=409, detail="ntfy ist nicht aktiviert")
    target.topic = new_topic()
    db.commit()
    return _out(target)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ntfy(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    target = db.get(NtfyTarget, user.id)
    if target is not None:
        db.delete(target)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
