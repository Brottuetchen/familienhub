"""Separate shopping and task lists (a packing list is not the grocery list).

A list can be assigned to one person. An item keeps its own assignee when set;
otherwise it follows the list. Items here never join the main shopping or task views.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import ROLE_LEVEL, get_current_user, require_min_role
from app.models.hub import HubShoppingItem, HubTask, NamedList
from app.models.user import ROLE_ADMIN, ROLE_PARTNER, User

router = APIRouter(prefix="/api/lists", tags=["lists"])


class ListIn(BaseModel):
    kind: Literal["shopping", "tasks"]
    name: str = Field(max_length=120)
    assignee_id: Optional[int] = None


class ListPatch(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    assignee_id: Optional[int] = None


class ItemIn(BaseModel):
    summary: str = Field(max_length=200)
    note: str = Field("", max_length=200)
    assignee_id: Optional[int] = None


class ItemPatch(BaseModel):
    summary: Optional[str] = Field(default=None, max_length=200)
    done: Optional[bool] = None
    assignee_id: Optional[int] = None


def _name(raw: str) -> str:
    name = re.sub(r"\s+", " ", raw or "").strip()
    if not name:
        raise HTTPException(422, "Name der Liste fehlt")
    return name[:120]


def _person(db: Session, user_id: Optional[int]) -> Optional[int]:
    if user_id is None:
        return None
    row = db.query(User).filter(User.id == user_id, User.is_active == True).first()  # noqa: E712
    if row is None:
        raise HTTPException(422, "Person nicht gefunden")
    return row.id


def _get(db: Session, list_id: int) -> NamedList:
    row = db.get(NamedList, list_id)
    if row is None:
        raise HTTPException(404, "Liste nicht gefunden")
    return row


def _items(db: Session, row: NamedList):
    if row.kind == "shopping":
        return db.query(HubShoppingItem).filter(HubShoppingItem.list_id == row.id).order_by(HubShoppingItem.id).all()
    return db.query(HubTask).filter(HubTask.list_id == row.id).order_by(HubTask.created_at).all()


def _item_out(row: NamedList, item) -> dict:
    own = item.assignee_id
    if row.kind == "shopping":
        return {"id": str(item.id), "summary": item.summary, "done": bool(item.done),
                "assignee_id": own if own is not None else row.assignee_id, "own_assignee": own is not None}
    return {"id": item.uid, "summary": item.title, "note": item.notes or "", "done": bool(item.done),
            "assignee_id": own if own is not None else row.assignee_id, "own_assignee": own is not None}


def _out(db: Session, row: NamedList, with_items: bool = False) -> dict:
    body = {"id": row.id, "kind": row.kind, "name": row.name, "assignee_id": row.assignee_id}
    if with_items:
        body["items"] = [_item_out(row, i) for i in _items(db, row)]
    return body


def _partner(user: User) -> None:
    role = user.role or (ROLE_ADMIN if user.is_admin else ROLE_PARTNER)
    level = ROLE_LEVEL[ROLE_ADMIN] if user.is_admin else ROLE_LEVEL.get(role, 0)
    if level < ROLE_LEVEL[ROLE_PARTNER]:
        raise HTTPException(403, "Requires at least role: partner")


def _touch(kind: str) -> None:
    from app.services import refresh

    refresh.schedule_refresh("shopping" if kind == "shopping" else "tasks")


def _apply_list_assignee(db: Session, row: NamedList, new_id: Optional[int]) -> None:
    old = row.assignee_id
    row.assignee_id = new_id
    for item in _items(db, row):
        if item.assignee_id is None or item.assignee_id == old:
            item.assignee_id = new_id


@router.get("")
def list_lists(kind: Literal["shopping", "tasks"], assignee_id: Optional[int] = None,
               with_items: bool = False,
               _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(NamedList).filter(NamedList.kind == kind)
    if assignee_id is not None:
        q = q.filter(NamedList.assignee_id == assignee_id)
    rows = q.order_by(NamedList.name, NamedList.id).all()
    return {"items": [_out(db, r, with_items=with_items) for r in rows]}


@router.post("", status_code=201)
def create_list(data: ListIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if data.kind == "tasks":
        _partner(user)
    row = NamedList(kind=data.kind, name=_name(data.name), assignee_id=_person(db, data.assignee_id),
                    created_by=user.id, created_at=datetime.utcnow())
    db.add(row)
    db.commit()
    db.refresh(row)
    _touch(row.kind)
    return _out(db, row, with_items=True)


@router.get("/{list_id}")
def get_list(list_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(db, _get(db, list_id), with_items=True)


@router.patch("/{list_id}")
def patch_list(list_id: int, data: ListPatch, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _get(db, list_id)
    if "name" in data.model_fields_set and data.name is not None:
        row.name = _name(data.name)
    if "assignee_id" in data.model_fields_set:
        _apply_list_assignee(db, row, _person(db, data.assignee_id))
    db.commit()
    _touch(row.kind)
    return _out(db, row, with_items=True)


@router.delete("/{list_id}", status_code=204)
def delete_list(list_id: int, _: User = Depends(require_min_role(ROLE_PARTNER)), db: Session = Depends(get_db)):
    row = _get(db, list_id)
    kind = row.kind
    for item in _items(db, row):
        db.delete(item)
    db.delete(row)
    db.commit()
    _touch(kind)


def _find_item(db: Session, row: NamedList, item_id: str):
    if row.kind == "shopping":
        if not item_id.isdigit():
            raise HTTPException(404, "Eintrag nicht gefunden")
        item = db.get(HubShoppingItem, int(item_id))
        if item is None or item.list_id != row.id:
            raise HTTPException(404, "Eintrag nicht gefunden")
        return item
    item = db.get(HubTask, item_id)
    if item is None or item.list_id != row.id:
        raise HTTPException(404, "Eintrag nicht gefunden")
    return item


@router.post("/{list_id}/items", status_code=201)
def add_item(list_id: int, data: ItemIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _get(db, list_id)
    summary = _name(data.summary)[:200]
    assignee = _person(db, data.assignee_id) if "assignee_id" in data.model_fields_set else None
    if row.kind == "shopping":
        text = f"{summary} ({data.note.strip()})" if data.note.strip() else summary
        item = HubShoppingItem(summary=text[:200], list_id=row.id, assignee_id=assignee, created_by=user.id)
        db.add(item)
    else:
        _partner(user)
        item = HubTask(uid=str(uuid.uuid4()), title=summary, notes=data.note.strip(), list_id=row.id,
                       assignee_id=assignee if assignee is not None else row.assignee_id,
                       created_by=user.id, family=False)
        db.add(item)
    db.commit()
    db.refresh(item)
    _touch(row.kind)
    return _item_out(row, item)


@router.patch("/{list_id}/items/{item_id}")
def patch_item(list_id: int, item_id: str, data: ItemPatch, _: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    row = _get(db, list_id)
    item = _find_item(db, row, item_id)
    if data.summary is not None:
        text = _name(data.summary)[:200]
        if row.kind == "shopping":
            item.summary = text
        else:
            item.title = text
    if data.done is not None:
        item.done = data.done
        item.completed_at = datetime.utcnow() if data.done else None
    if "assignee_id" in data.model_fields_set:
        item.assignee_id = _person(db, data.assignee_id)
    db.commit()
    _touch(row.kind)
    return _item_out(row, item)


def add_from_template(db: Session, user: User, kind: str, name: str, assignee_id: Optional[int], items) -> NamedList:
    """Create a separate list from template items. Does not touch the main shopping or task list."""
    assignee = _person(db, assignee_id)
    row = NamedList(kind=kind, name=_name(name), assignee_id=assignee, created_by=user.id, created_at=datetime.utcnow())
    db.add(row)
    db.flush()
    for item in items:
        note = (item.note or "").strip()
        if kind == "shopping":
            text = f"{item.name} ({note})" if note else item.name
            db.add(HubShoppingItem(summary=text[:200], list_id=row.id, assignee_id=assignee, created_by=user.id))
        else:
            db.add(HubTask(uid=str(uuid.uuid4()), title=item.name[:200], notes=note, list_id=row.id,
                           assignee_id=assignee, created_by=user.id, family=False))
    db.commit()
    db.refresh(row)
    _touch(kind)
    return row
