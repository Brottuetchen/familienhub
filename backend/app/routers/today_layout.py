"""Customisable "Today" screen: own layout and the family default (admin)."""

from __future__ import annotations

from typing import List, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_admin_user, get_current_user
from app.models.user import User
from app.services import today_layout as svc

router = APIRouter(tags=["today-layout"])


class Card(BaseModel):
    id: str
    visible: bool = True
    size: Literal["full", "half"] = "full"

    @field_validator("id")
    @classmethod
    def _known(cls, v):
        if v not in svc.KNOWN:
            raise ValueError("unknown card id")
        return v


class LayoutIn(BaseModel):
    cards: List[Card] = Field(max_length=len(svc.KNOWN))

    @field_validator("cards")
    @classmethod
    def _unique(cls, v):
        ids = [c.id for c in v]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate card id")
        return v


def _cards(body: LayoutIn) -> list:
    return svc.normalize([c.model_dump() for c in body.cards])


@router.get("/api/me/today-layout")
async def get_layout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.effective(db, user.id)


@router.put("/api/me/today-layout")
async def put_layout(body: LayoutIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc.save_own(db, user.id, _cards(body))
    return svc.effective(db, user.id)


@router.delete("/api/me/today-layout")
async def reset_layout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Back to the family default (or the built-in one)."""
    svc.reset_own(db, user.id)
    return svc.effective(db, user.id)


@router.get("/api/admin/today-layout")
async def get_default(_: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    cards = svc.family_default(db)
    return {"cards": cards or svc.normalize([]), "source": "family" if cards else "builtin"}


@router.put("/api/admin/today-layout")
async def put_default(body: LayoutIn, _: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    svc.save_family_default(db, _cards(body))
    return {"cards": svc.family_default(db), "source": "family"}


@router.delete("/api/admin/today-layout")
async def reset_default(_: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    svc.reset_family_default(db)
    return {"cards": svc.normalize([]), "source": "builtin"}
