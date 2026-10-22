"""Reusable template lists (#20): packing lists, the weekly shopping, ...

Templates belong to the family. Everybody can read them; partners and admins create, change and delete them. A
template is applied either to the shopping list (whatever source is active: hub, Home Assistant, Mealie), which
every role may add to, or to the tasks as one task per item, which needs the same role as creating a task.
"""

from __future__ import annotations

import logging
import re
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_min_role
from app.models.list_template import ListTemplate, ListTemplateItem
from app.models.user import ROLE_PARTNER, User

router = APIRouter(prefix="/api/templates", tags=["templates"])
logger = logging.getLogger("hermes.templates")

MAX_ITEMS = 200


class TemplateItemIn(BaseModel):
    name: str = Field(max_length=200)
    note: str = Field("", max_length=200)


class TemplateIn(BaseModel):
    name: str = Field(max_length=120)
    items: List[TemplateItemIn] = Field(default_factory=list, max_length=MAX_ITEMS)


class FromShoppingIn(BaseModel):
    name: str = Field(max_length=120)


class ApplyIn(BaseModel):
    item_ids: Optional[List[int]] = Field(None, max_length=MAX_ITEMS)  # None = all items
    list: Optional[str] = None  # tasks only: "family" for the family list


def norm(text: str) -> str:
    """Case- and whitespace-insensitive key."""
    return re.sub(r"\s+", " ", text or "").strip().casefold()


def _clean(items: List[TemplateItemIn]):
    out = []
    for i in items:
        name, note = re.sub(r"\s+", " ", i.name).strip(), re.sub(r"\s+", " ", i.note).strip()
        if name:
            out.append((name, note))
    return out


def _out(t: ListTemplate):
    return {"id": t.id, "name": t.name, "item_count": len(t.items),
            "items": [{"id": i.id, "name": i.name, "note": i.note} for i in t.items]}


def _get(db: Session, template_id: int) -> ListTemplate:
    t = db.get(ListTemplate, template_id)
    if t is None:
        raise HTTPException(404, "Vorlage nicht gefunden")
    return t


def _fill(t: ListTemplate, items) -> None:
    t.items = [ListTemplateItem(position=n, name=name, note=note) for n, (name, note) in enumerate(items)]


def _name(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        raise HTTPException(422, "Name der Vorlage fehlt")
    return name


def _chosen(t: ListTemplate, data: ApplyIn):
    items = t.items if data.item_ids is None else [i for i in t.items if i.id in set(data.item_ids)]
    if data.item_ids is not None and not items:
        raise HTTPException(422, "Keine Einträge ausgewählt")
    return items


def shopping_text(name: str, note: str) -> str:
    return f"{name} ({note})" if note else name


@router.get("")
def list_templates(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(ListTemplate).order_by(ListTemplate.name, ListTemplate.id).all()
    return {"items": [_out(t) for t in rows]}


@router.post("", status_code=201)
def create_template(data: TemplateIn, user: User = Depends(require_min_role(ROLE_PARTNER)),
                    db: Session = Depends(get_db)):
    t = ListTemplate(name=_name(data.name), created_by=user.id)
    _fill(t, _clean(data.items))
    db.add(t)
    db.commit()
    db.refresh(t)
    return _out(t)


@router.post("/from-shopping", status_code=201)
async def template_from_shopping(data: FromShoppingIn, user: User = Depends(require_min_role(ROLE_PARTNER)),
                                 db: Session = Depends(get_db)):
    """Saves the open entries of the current shopping list as a template."""
    from app.routers.shopping import open_shopping_summaries

    summaries = await open_shopping_summaries()
    if summaries is None:
        raise HTTPException(503, "Einkaufsliste nicht verfügbar")
    seen, items = set(), []
    for s in summaries:
        key = norm(s)
        if key and key not in seen:
            seen.add(key)
            items.append((re.sub(r"\s+", " ", s).strip()[:200], ""))
    if not items:
        raise HTTPException(422, "Die Einkaufsliste ist leer")
    t = ListTemplate(name=_name(data.name), created_by=user.id)
    _fill(t, items)
    db.add(t)
    db.commit()
    db.refresh(t)
    return _out(t)


@router.get("/{template_id}")
def get_template(template_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(_get(db, template_id))


@router.put("/{template_id}")
def update_template(template_id: int, data: TemplateIn, _: User = Depends(require_min_role(ROLE_PARTNER)),
                    db: Session = Depends(get_db)):
    t = _get(db, template_id)
    t.name = _name(data.name)
    _fill(t, _clean(data.items))
    db.commit()
    db.refresh(t)
    return _out(t)


@router.delete("/{template_id}", status_code=204)
def delete_template(template_id: int, _: User = Depends(require_min_role(ROLE_PARTNER)),
                    db: Session = Depends(get_db)):
    db.delete(_get(db, template_id))
    db.commit()


@router.post("/{template_id}/apply/shopping")
async def apply_to_shopping(template_id: int, data: ApplyIn, user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    """Adds the (chosen) items to the shopping list; entries that are already open there are not added twice."""
    from app.routers.shopping import add_to_shopping, open_shopping_summaries

    items = _chosen(_get(db, template_id), data)
    open_texts = await open_shopping_summaries()
    if open_texts is None:
        return {"status": "unavailable", "added": 0, "skipped": 0, "failed": 0}
    have = {norm(s) for s in open_texts}
    # "Milch (2 l)" on the list also counts as "Milch"
    have |= {norm(re.sub(r"\s*\([^)]*\)\s*$", "", s)) for s in open_texts}
    todo, skipped = [], 0
    for i in items:
        text = shopping_text(i.name, i.note)
        if norm(i.name) in have or norm(text) in have:
            skipped += 1
            continue
        have.add(norm(i.name))
        todo.append(text)
    added = await add_to_shopping(todo, user.id) if todo else 0
    return {"status": "ok", "added": added, "skipped": skipped, "failed": len(todo) - added}


@router.post("/{template_id}/apply/tasks")
async def apply_to_tasks(template_id: int, data: ApplyIn, user: User = Depends(require_min_role(ROLE_PARTNER)),
                         db: Session = Depends(get_db)):
    """Creates one task per (chosen) item, placed like any new task (``provider=auto``): in the person's own task
    source, or the family list with ``list="family"``. The note becomes the task's notes."""
    from app.routers.tasks import TaskCreateRequest, _create_task

    if data.list not in (None, "family"):
        raise HTTPException(422, "Ungültige Liste")
    t = _get(db, template_id)
    created, failed = 0, 0
    for i in _chosen(t, data):
        try:
            req = TaskCreateRequest(title=i.name, notes=i.note or None, list=data.list)
            await _create_task(req, "auto", None, user, db)
            created += 1
        except HTTPException as exc:
            failed += 1
            logger.warning("Task from template not created: %s", exc.status_code)
        except Exception as exc:  # noqa: BLE001 - one failed item must not stop the others
            failed += 1
            logger.warning("Task from template not created: %s", type(exc).__name__)
    return {"status": "ok" if not failed else "partial", "created": created, "failed": failed}


class ApplyListIn(BaseModel):
    name: str = Field(max_length=120)
    kind: Literal["shopping", "tasks"]
    assignee_id: Optional[int] = None
    item_ids: Optional[List[int]] = Field(None, max_length=MAX_ITEMS)


@router.post("/{template_id}/apply/list", status_code=201)
def apply_as_list(template_id: int, data: ApplyListIn, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Creates a separate list. Does not add to the main shopping or task list."""
    from app.routers.lists import _out, _partner, add_from_template

    if data.kind == "tasks":
        _partner(user)
    items = _chosen(_get(db, template_id), ApplyIn(item_ids=data.item_ids))
    row = add_from_template(db, user, data.kind, data.name, data.assignee_id, items)
    return _out(db, row, with_items=True)
