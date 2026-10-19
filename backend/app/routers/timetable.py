"""Timetable of children. Parents (partner/admin) edit, a child views their own, enforced here."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_min_role
from app.core.timeutil import local_tz
from app.models.timetable import TimetableEntry, TimetableSource
from app.models.user import ROLE_PARTNER, User
from app.services import timetable as svc
from app.services import timetable_plugin as plug

router = APIRouter(prefix="/api/timetable", tags=["timetable"])
parent = require_min_role(ROLE_PARTNER)

Week = Literal["all", "a", "b"]
Kind = Literal["school", "sport", "music", "club", "other"]
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class EntryIn(BaseModel):
    child_id: int
    weekday: int = Field(ge=0, le=6)
    week: Week = "all"
    start: str
    end: str
    title: str = Field(min_length=1, max_length=80)
    kind: Kind = "school"
    location: Optional[str] = Field(default=None, max_length=80)

    @field_validator("start", "end")
    @classmethod
    def _time(cls, v):
        if not _TIME.match(v):
            raise ValueError("time must be HH:MM")
        return v

    @field_validator("title")
    @classmethod
    def _strip(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("title required")
        return v

    @model_validator(mode="after")
    def _order(self):
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class EntryPatch(BaseModel):
    weekday: Optional[int] = Field(default=None, ge=0, le=6)
    week: Optional[Week] = None
    start: Optional[str] = None
    end: Optional[str] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=80)
    kind: Optional[Kind] = None
    location: Optional[str] = Field(default=None, max_length=80)


class CopyDay(BaseModel):
    child_id: int
    week: Week = "all"
    from_weekday: int = Field(ge=0, le=6)
    to_weekdays: List[int] = Field(min_length=1, max_length=7)
    to_week: Optional[Week] = None

    @field_validator("to_weekdays")
    @classmethod
    def _days(cls, v):
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("weekday 0-6")
        return v


class CopyWeek(BaseModel):
    child_id: int
    from_week: Week
    to_week: Week


class SettingsIn(BaseModel):
    ab_reference: Optional[date] = None
    holiday_feed: Optional[str] = Field(default=None, max_length=120)


def _child(db: Session, child_id: int) -> User:
    kid = db.get(User, child_id)
    if kid is None or kid.role != "child":
        raise HTTPException(404, "Child not found")
    return kid


def _settings_payload(db: Session) -> dict:
    return {**svc.get_settings(db), "feeds": svc.available_feeds()}


@router.get("/children")
async def children(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [{"id": k.id, "name": k.effective_name} for k in svc.children_visible_to(db, user)]


@router.get("")
async def get_timetable(child_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if child_id not in {k.id for k in svc.children_visible_to(db, user)}:
        raise HTTPException(403, "Not allowed to see this timetable")
    kid = _child(db, child_id)
    rows = (db.query(TimetableEntry).filter_by(child_id=kid.id)
            .order_by(TimetableEntry.weekday, TimetableEntry.start, TimetableEntry.id).all())
    today = datetime.now(local_tz()).date()
    return {
        "child": {"id": kid.id, "name": kid.effective_name},
        "entries": [svc.serialize(r) for r in rows],
        "settings": _settings_payload(db),
        "current_week": svc.week_variant(db, today),
        "holidays": await svc.holidays(db, today, today + timedelta(days=90)),
        "can_edit": svc.is_parent(user),
        "plugin": svc.plugin_info(plug.source_of(db, kid.id), "ok"),
    }


@router.get("/week")
async def get_week(child_id: int, start: Optional[date] = None, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """One calendar week (Monday first) of a child with real dates: manual entries merged with the lessons of the
    plugin the child is mapped to (cancelled and substituted lessons carry a ``status``). Fails softly."""
    if child_id not in {k.id for k in svc.children_visible_to(db, user)}:
        raise HTTPException(403, "Not allowed to see this timetable")
    kid = _child(db, child_id)
    return await svc.week_view(db, kid, start or datetime.now(local_tz()).date())


class SourceIn(BaseModel):
    child_id: int
    plugin_id: Optional[str] = Field(default=None, max_length=40)
    person_id: Optional[str] = Field(default=None, max_length=200)


class SourcesIn(BaseModel):
    sources: List[SourceIn] = Field(max_length=50)


async def _sources_payload(db: Session) -> dict:
    kids = db.query(User).filter(User.role == "child", User.is_active.is_(True)).order_by(User.id).all()
    rows = {r.child_id: r for r in db.query(TimetableSource).all()}
    plugins = []
    for p in plug.timetable_plugins():
        listed, trusted = await plug.people(p)
        plugins.append({"id": p.id, "name": p.name, "people": listed, "people_known": trusted})
    return {
        "children": [{"child_id": k.id, "name": k.effective_name, "plugin_id": rows[k.id].plugin_id if k.id in rows else None,
                      "person_id": rows[k.id].person_id if k.id in rows else None,
                      "person_name": rows[k.id].person_name if k.id in rows else None} for k in kids],
        "plugins": plugins,
    }


@router.get("/sources")
async def get_sources(_: User = Depends(parent), db: Session = Depends(get_db)):
    """Per child: which plugin provides the timetable and who the child is there; plus the plugins that can."""
    return await _sources_payload(db)


@router.put("/sources")
async def put_sources(body: SourcesIn, _: User = Depends(parent), db: Session = Depends(get_db)):
    """Map children to plugin people. ``plugin_id`` or ``person_id`` empty removes the mapping of that child.
    When the plugin lists its people (``timetable_people``), the identifier must be one of them."""
    available = {p.id: p for p in plug.timetable_plugins()}
    listed: dict = {}
    for item in body.sources:
        _child(db, item.child_id)
        plugin_id = (item.plugin_id or "").strip() or None
        person_id = (item.person_id or "").strip() or None
        name = None
        if plugin_id and person_id:
            if plugin_id not in available:
                raise HTTPException(422, "Plugin provides no timetable")
            if plugin_id not in listed:
                listed[plugin_id] = await plug.people(available[plugin_id])
            people, trusted = listed[plugin_id]
            if trusted and people:
                match = next((p for p in people if p["id"] == person_id), None)
                if match is None:
                    raise HTTPException(422, "Unknown person for this plugin")
                name = match["name"]
        plug.save_source(db, item.child_id, plugin_id, person_id, name)
    db.commit()
    plug.clear_cache()
    return await _sources_payload(db)


@router.get("/today")
async def timetable_today(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return await svc.today_card(db, user, datetime.now(local_tz()).date())


@router.get("/settings")
async def get_settings(_: User = Depends(parent), db: Session = Depends(get_db)):
    return _settings_payload(db)


@router.put("/settings")
async def put_settings(body: SettingsIn, _: User = Depends(parent), db: Session = Depends(get_db)):
    feed = (body.holiday_feed or "").strip() or None
    if feed and feed not in {f["id"] for f in svc.available_feeds()}:
        raise HTTPException(422, "Unknown calendar subscription")
    svc.save_settings(db, body.ab_reference, feed)
    return _settings_payload(db)


@router.post("", status_code=201)
async def create_entry(body: EntryIn, _: User = Depends(parent), db: Session = Depends(get_db)):
    _child(db, body.child_id)
    row = TimetableEntry(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return svc.serialize(row)


@router.patch("/{entry_id}")
async def update_entry(entry_id: int, body: EntryPatch, _: User = Depends(parent), db: Session = Depends(get_db)):
    row = db.get(TimetableEntry, entry_id)
    if row is None:
        raise HTTPException(404, "Entry not found")
    data = body.model_dump(exclude_unset=True)
    for key in ("start", "end"):
        if key in data and not _TIME.match(data[key] or ""):
            raise HTTPException(422, "time must be HH:MM")
    for key, value in data.items():
        if value is None and key != "location":
            continue
        setattr(row, key, value.strip() if key == "title" else value)
    if row.end <= row.start:
        raise HTTPException(422, "end must be after start")
    db.commit()
    return svc.serialize(row)


@router.delete("/{entry_id}", status_code=204)
async def delete_entry(entry_id: int, _: User = Depends(parent), db: Session = Depends(get_db)):
    row = db.get(TimetableEntry, entry_id)
    if row is None:
        raise HTTPException(404, "Entry not found")
    db.delete(row)
    db.commit()


@router.post("/copy-day")
async def copy_day(body: CopyDay, _: User = Depends(parent), db: Session = Depends(get_db)):
    _child(db, body.child_id)
    return {"copied": svc.copy_day(db, body.child_id, body.week, body.from_weekday, body.to_weekdays, body.to_week)}


@router.post("/copy-week")
async def copy_week(body: CopyWeek, _: User = Depends(parent), db: Session = Depends(get_db)):
    _child(db, body.child_id)
    if body.from_week == body.to_week:
        raise HTTPException(422, "Source and target week are the same")
    return {"copied": svc.copy_week(db, body.child_id, body.from_week, body.to_week)}
