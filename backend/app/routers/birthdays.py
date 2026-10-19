"""Birthdays and anniversaries with gift ideas.

Permissions:
- guests: nothing (403), they are outside the family;
- children: read the list, add gift ideas, tick them off and remove their own;
- partners/admins: additionally create, edit and delete entries and remove any gift idea.
- Gift ideas of an entry linked to a hub user are invisible to that user (404, enforced here for
  every role including admins): the surprise stays one.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import ROLE_LEVEL, get_current_user, require_min_role
from app.core.timeutil import local_tz
from app.models.birthday import Birthday, GiftIdea
from app.models.user import ROLE_PARTNER, User
from app.services import birthdays as svc

router = APIRouter(prefix="/api/birthdays", tags=["birthdays"])

Kind = Literal["birthday", "anniversary"]


def _viewer(current_user: User = Depends(get_current_user)) -> User:
    if not svc.can_view(current_user):
        raise HTTPException(status_code=403, detail="Geburtstage sind für Gäste nicht sichtbar")
    return current_user


def _is_adult(user: User) -> bool:
    return bool(user.is_admin) or ROLE_LEVEL.get(user.role or ROLE_PARTNER, 0) >= ROLE_LEVEL[ROLE_PARTNER]


def _today() -> date:
    return datetime.now(local_tz()).date()


class BirthdayIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: Kind = "birthday"
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)
    year: Optional[int] = Field(default=None, ge=1, le=9999)
    user_id: Optional[int] = None  # hub user this entry belongs to: they never see its gift ideas
    remind_days_before: Optional[int] = Field(default=7, ge=0, le=60)  # None = no reminder

    @model_validator(mode="after")
    def _date(self):
        if not svc.valid_date(self.month, self.day, self.year):
            raise ValueError("Ungültiges Datum")
        return self


def _out(row: Birthday, viewer: User, gifts: int) -> Dict[str, Any]:
    linked_to_me = row.user_id is not None and row.user_id == viewer.id
    return {
        "id": row.id, "name": row.name, "kind": row.kind, "month": row.month, "day": row.day, "year": row.year,
        "user_id": row.user_id, "remind_days_before": row.remind_days_before, "is_you": linked_to_me,
        # the person themselves gets no hint that gift ideas exist
        "gift_count": None if linked_to_me else gifts,
        **svc.describe(row, _today()),
    }


def _gift_counts(db: Session) -> Dict[int, int]:
    from sqlalchemy import func

    return dict(db.query(GiftIdea.birthday_id, func.count(GiftIdea.id)).filter(GiftIdea.done == False)  # noqa: E712
                .group_by(GiftIdea.birthday_id).all())


def _check_user(db: Session, user_id: Optional[int]) -> None:
    if user_id is not None and not db.get(User, user_id):
        raise HTTPException(status_code=422, detail="Person nicht gefunden")


@router.get("")
async def list_birthdays(db: Session = Depends(get_db), viewer: User = Depends(_viewer)):
    counts = _gift_counts(db)
    items = [_out(r, viewer, counts.get(r.id, 0)) for r in svc.visible_rows(db, viewer)]
    items.sort(key=lambda b: (b["days_until"], b["name"].lower()))
    return items


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_birthday(data: BirthdayIn, db: Session = Depends(get_db),
                          current_user: User = Depends(require_min_role(ROLE_PARTNER))):
    _check_user(db, data.user_id)
    row = Birthday(**data.model_dump(), created_by=current_user.id)
    row.name = row.name.strip()
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row, current_user, 0)


@router.put("/{birthday_id}")
async def update_birthday(birthday_id: int, data: BirthdayIn, db: Session = Depends(get_db),
                          current_user: User = Depends(require_min_role(ROLE_PARTNER))):
    row = db.get(Birthday, birthday_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")
    _check_user(db, data.user_id)
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    row.name = row.name.strip()
    db.commit()
    db.refresh(row)
    return _out(row, current_user, _gift_counts(db).get(row.id, 0))


@router.delete("/{birthday_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_birthday(birthday_id: int, db: Session = Depends(get_db),
                          current_user: User = Depends(require_min_role(ROLE_PARTNER))):
    row = db.get(Birthday, birthday_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")
    db.query(GiftIdea).filter(GiftIdea.birthday_id == row.id).delete()  # SQLite does not cascade
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- gift ideas --------------------------------------------------------------------------------------------------


def _gift_entry(db: Session, birthday_id: int, viewer: User) -> Birthday:
    """The entry, or 404 - also for the linked person, so they cannot even tell that ideas exist."""
    row = db.get(Birthday, birthday_id)
    if row is None or (row.user_id is not None and row.user_id == viewer.id):
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")
    return row


def _gift_out(g: GiftIdea) -> Dict[str, Any]:
    return {"id": g.id, "birthday_id": g.birthday_id, "text": g.text, "link": g.link, "done": bool(g.done),
            "created_by": g.created_by}


class GiftIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    link: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _link(self):
        if self.link and not self.link.strip().lower().startswith(("http://", "https://")):
            raise ValueError("Link muss mit http:// oder https:// beginnen")
        return self


class GiftPatch(BaseModel):
    text: Optional[str] = Field(default=None, min_length=1, max_length=300)
    link: Optional[str] = Field(default=None, max_length=500)
    done: Optional[bool] = None

    @model_validator(mode="after")
    def _link(self):
        if self.link and not self.link.strip().lower().startswith(("http://", "https://")):
            raise ValueError("Link muss mit http:// oder https:// beginnen")
        return self


@router.get("/{birthday_id}/gifts")
async def list_gifts(birthday_id: int, db: Session = Depends(get_db), viewer: User = Depends(_viewer)):
    _gift_entry(db, birthday_id, viewer)
    rows = db.query(GiftIdea).filter(GiftIdea.birthday_id == birthday_id).order_by(GiftIdea.done, GiftIdea.id).all()
    return [_gift_out(g) for g in rows]


@router.post("/{birthday_id}/gifts", status_code=status.HTTP_201_CREATED)
async def add_gift(birthday_id: int, data: GiftIn, db: Session = Depends(get_db), viewer: User = Depends(_viewer)):
    _gift_entry(db, birthday_id, viewer)
    gift = GiftIdea(birthday_id=birthday_id, text=data.text.strip(), link=(data.link or "").strip() or None,
                    created_by=viewer.id)
    db.add(gift)
    db.commit()
    db.refresh(gift)
    return _gift_out(gift)


def _gift(db: Session, birthday_id: int, gift_id: int, viewer: User) -> GiftIdea:
    _gift_entry(db, birthday_id, viewer)
    gift = db.get(GiftIdea, gift_id)
    if gift is None or gift.birthday_id != birthday_id:
        raise HTTPException(status_code=404, detail="Geschenkidee nicht gefunden")
    return gift


@router.patch("/{birthday_id}/gifts/{gift_id}")
async def update_gift(birthday_id: int, gift_id: int, data: GiftPatch, db: Session = Depends(get_db),
                      viewer: User = Depends(_viewer)):
    gift = _gift(db, birthday_id, gift_id, viewer)
    changes = data.model_dump(exclude_unset=True)
    edits_content = bool({"text", "link"} & set(changes))
    if edits_content and not (_is_adult(viewer) or gift.created_by == viewer.id):
        raise HTTPException(status_code=403, detail="Nur eigene Geschenkideen ändern")
    if "text" in changes and changes["text"]:
        gift.text = changes["text"].strip()
    if "link" in changes:
        gift.link = (changes["link"] or "").strip() or None
    if "done" in changes and changes["done"] is not None:
        gift.done = changes["done"]
    db.commit()
    db.refresh(gift)
    return _gift_out(gift)


@router.delete("/{birthday_id}/gifts/{gift_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_gift(birthday_id: int, gift_id: int, db: Session = Depends(get_db), viewer: User = Depends(_viewer)):
    gift = _gift(db, birthday_id, gift_id, viewer)
    if not (_is_adult(viewer) or gift.created_by == viewer.id):
        raise HTTPException(status_code=403, detail="Nur eigene Geschenkideen löschen")
    db.delete(gift)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
