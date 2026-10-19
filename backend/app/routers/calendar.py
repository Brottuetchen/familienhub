"""Calendar endpoints: the person's CalDAV calendars plus the hub's family calendar (``hub_calendar``)."""

from __future__ import annotations

import logging

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.connectors.registry import registry
from app.core.database import get_db
from app.core.security import get_current_user, require_min_role
from app.models.caldav import CalDAVAccount
from app.models.user import User, ROLE_PARTNER
from app.services.holidays import upcoming_holidays

router = APIRouter(prefix="/api/calendar", tags=["calendar"])
logger = logging.getLogger("hermes.calendar")


class EventCreateRequest(BaseModel):
    """Neuen Kalendereintrag erstellen."""

    title: str = Field(min_length=1, max_length=200)
    start: str  # ISO 8601
    end: str  # ISO 8601
    all_day: bool
    calendar_url: Optional[str] = None
    # Target: the person's CalDAV calendar or the hub's family calendar. Default: CalDAV if set up, else hub.
    source: Optional[Literal["caldav", "hub"]] = None
    # Exact target from GET /calendars ("hub" or "caldav:<id>"); takes precedence over source/calendar_url
    calendar_id: Optional[str] = Field(default=None, max_length=60)
    location: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=2000)
    recurrence: Literal["none", "daily", "weekly", "monthly", "yearly"] = "none"
    # Reminder in minutes before the start (0 = at the start); None = no reminder
    alarm_minutes: Optional[int] = Field(default=None, ge=0, le=10080)

    @model_validator(mode="after")
    def _times(self):
        try:
            start, end = _parse(self.start), _parse(self.end)
        except ValueError as exc:
            raise ValueError("Start und Ende als ISO-Datum angeben") from exc
        if end < start:
            raise ValueError("Ende liegt vor dem Start")
        return self


def _parse(value: str) -> datetime:
    """ISO date or date-time as local wall time (an offset is dropped after conversion to local time)."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        from app.core.timeutil import local_tz

        dt = dt.astimezone(local_tz()).replace(tzinfo=None)
    return dt


def _hub_active() -> bool:
    from app.plugins.registry import plugin_registry

    return plugin_registry.serves("calendar", "hub_calendar")


def _caldav_active() -> bool:
    from app.plugins.registry import plugin_registry

    return plugin_registry.serves("calendar", "nextcloud")


RRULE = {"daily": "DAILY", "weekly": "WEEKLY", "monthly": "MONTHLY", "yearly": "YEARLY"}


def _hub_event(e, start: Optional[datetime] = None) -> Dict[str, Any]:
    """Hub event as JSON; with ``start`` one occurrence of a repeating event."""
    begin = start or e.start
    finish = begin + (e.end - e.start)
    fmt = (lambda d: d.date().isoformat()) if e.all_day else (lambda d: d.isoformat())
    return {"id": e.id, "title": e.title, "start": fmt(begin), "end": fmt(finish), "all_day": bool(e.all_day),
            "location": e.location, "notes": getattr(e, "notes", None), "recurrence": getattr(e, "recurrence", None) or "none",
            "alarm_minutes": getattr(e, "alarm_minutes", None),
            "calendar": "Familie", "calendar_id": "hub", "source": "hub"}


def _hub_occurrences(e, window_start: datetime, window_end: datetime) -> List[Dict[str, Any]]:
    rec = getattr(e, "recurrence", None) or "none"
    if rec == "none":
        return [_hub_event(e)]
    from dateutil.rrule import rrulestr

    rule = rrulestr(f"RRULE:FREQ={RRULE[rec]}", dtstart=e.start)
    length = e.end - e.start
    return [_hub_event(e, s) for s in rule.between(window_start - length, window_end, inc=True)[:400]]


async def collect_events(db: Session, user: User, days: int, start: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """All events of the time window: CalDAV (own account, else the shared one) and the hub calendar."""
    from app.models.hub import HubEvent

    start = start or datetime.now()
    end = start + timedelta(days=days)
    events: List[Dict[str, Any]] = []
    if _caldav_active():
        try:
            caldav_events = await connector_for_user(db, user).get_events(days_ahead=days, start=start)
            events.extend({**e, "source": e.get("source", "caldav")} for e in (caldav_events or []))
        except HTTPException:
            pass  # CalDAV connector switched off: the other sources still count
    from app.plugins.registry import plugin_registry

    if plugin_registry.serves("calendar", "ics"):
        from app.services import ics

        events.extend(await ics.events_between(start, end))
    if _hub_active():
        midnight = start.replace(hour=0, minute=0, second=0, microsecond=0)
        rows = db.query(HubEvent).filter(HubEvent.start < end).filter(
            (HubEvent.end >= midnight) | (HubEvent.recurrence != "none")).all()
        for e in rows:
            events.extend(o for o in _hub_occurrences(e, midnight, end) if o["end"] >= midnight.date().isoformat())
    events.extend(_birthday_events(db, user, start, end))
    events.sort(key=lambda e: e.get("start") or "")
    return events


def _birthday_events(db: Session, user: User, start: datetime, end: datetime) -> List[Dict[str, Any]]:
    """Read-only virtual calendar of birthdays and anniversaries (not for guests); never breaks the calendar."""
    from app.services import birthdays

    try:
        return birthdays.calendar_events(birthdays.visible_rows(db, user), start.date(), end.date() + timedelta(days=1))
    except Exception as exc:  # noqa: BLE001 - fail softly
        logger.warning("birthdays skipped: %s", type(exc).__name__)
        return []


def _user_account(db: Session, user: User) -> Optional[CalDAVAccount]:
    return db.query(CalDAVAccount).filter(CalDAVAccount.user_id == user.id).first()


def connector_for_user(db: Session, user: User):
    """CalDAV-Connector mit dem Konto des Nutzers, sonst der globale (Familienkalender)."""
    account = _user_account(db, user)
    if account:
        from app.connectors.caldav_connector import CalDAVConnector
        from app.core.crypto import decrypt

        return CalDAVConnector(
            url=account.url,
            username=account.username,
            password=decrypt(account.password_enc),
        )
    c = registry.get("caldav")
    if not c:
        raise HTTPException(status_code=503, detail="Calendar connector unavailable")
    return c


@router.get("/today")
async def today(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return await connector_for_user(db, current_user).get_today()


@router.get("/events")
async def events(
    days: int = 7,
    start: Optional[date] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Events from all sources; with ``start`` (YYYY-MM-DD) a whole month or week, also in the past."""
    days = max(1, min(days, 400))
    begin = datetime.combine(start, datetime.min.time()) if start else None
    return await collect_events(db, current_user, days, start=begin)


@router.get("/calendars")
async def calendars(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """All calendars the person sees, for colours, filters and choosing where a new event goes.

    ``writable``: events can be created there by this person (family calendar from partner on, own CalDAV calendars).
    """
    from app.core.security import ROLE_LEVEL
    from app.models.user import ROLE_PARTNER
    from app.plugins.base import get_setting
    from app.plugins.registry import plugin_registry
    from app.services.ics import parse_feeds

    can_edit = current_user.is_admin or ROLE_LEVEL.get(current_user.role or ROLE_PARTNER, 0) >= ROLE_LEVEL[ROLE_PARTNER]
    out: List[Dict[str, Any]] = []
    if _hub_active():
        out.append({"id": "hub", "name": "Familie", "source": "hub", "color": None, "writable": can_edit, "family": True})
    if _caldav_active() and _user_account(db, current_user):
        family_names = {n.strip().lower() for n in str(get_setting("CALDAV_FAMILY_CALENDAR") or "").split(",") if n.strip()}
        for c in await connector_for_user(db, current_user).list_calendars():
            out.append({"id": c["id"], "name": c["name"], "source": "caldav", "color": c.get("color"),
                        "writable": can_edit, "family": c["name"].strip().lower() in family_names})
    out.sort(key=lambda c: (not c["family"], c["source"] == "ics"))  # family calendars first: default target
    if plugin_registry.serves("calendar", "ics"):
        from app.services.ics import feed_id

        for name, _url in parse_feeds(get_setting("ICS_FEEDS")):
            out.append({"id": feed_id(name), "name": name, "source": "ics", "color": None, "writable": False, "family": True})
    from app.services import birthdays

    if birthdays.visible_rows(db, current_user):  # the chip only appears once there is something to show
        out.append({"id": birthdays.CALENDAR_ID, "name": birthdays.CALENDAR_NAME, "source": "birthdays", "color": None,
                    "writable": False, "family": True})
    return out


@router.get("/holidays")
async def holidays(days: int = 60, current_user: User = Depends(get_current_user)):
    """Deutsche Feiertage (bundesweit) in den nächsten Tagen."""
    return upcoming_holidays(days=days)


@router.post("/events", status_code=status.HTTP_201_CREATED)
async def create_event(
    event: EventCreateRequest,
    current_user: User = Depends(require_min_role(ROLE_PARTNER)),
    db: Session = Depends(get_db),
):
    """Erstellt einen Termin: per CalDAV mit dem Konto des Nutzers oder im Familienkalender des Hubs.

    Ohne CalDAV-Konto geht der Termin in den Hub-Kalender (wenn aktiv), sonst 409 no_caldav_account.
    Der globale Kalenderzugang wird bewusst nicht verwendet, damit Termine dem richtigen Nutzer gehören.
    """
    has_account = _caldav_active() and _user_account(db, current_user) is not None
    target_url = event.calendar_url
    if event.calendar_id and event.calendar_id != "hub":
        if not event.calendar_id.startswith("caldav:") or not has_account:
            raise HTTPException(status_code=422, detail="In diesen Kalender kann der Hub nicht schreiben")
        match = [c for c in await connector_for_user(db, current_user).list_calendars() if c["id"] == event.calendar_id]
        if not match:
            raise HTTPException(status_code=422, detail="Kalender nicht gefunden")
        target_url = match[0]["url"]
    if event.calendar_id == "hub" or (event.calendar_id is None and (
            event.source == "hub" or (event.source is None and not has_account and _hub_active()))):
        if not _hub_active():
            raise HTTPException(status_code=409, detail="Der Familienkalender im Hub ist abgeschaltet")
        from app.models.hub import HubEvent

        row = HubEvent(title=event.title.strip(), start=_parse(event.start), end=_parse(event.end),
                       all_day=event.all_day, location=(event.location or "").strip() or None,
                       notes=(event.notes or "").strip() or None, recurrence=event.recurrence,
                       alarm_minutes=event.alarm_minutes, created_by=current_user.id)
        db.add(row)
        db.commit()
        return _hub_event(row)
    if not has_account:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "no_caldav_account"},
        )
    connector = connector_for_user(db, current_user)
    extras = {k: v for k, v in {"location": (event.location or "").strip(), "notes": (event.notes or "").strip(),
                                 "rrule": RRULE.get(event.recurrence)}.items() if v}
    if event.alarm_minutes is not None:
        extras["alarm_minutes"] = event.alarm_minutes  # 0 (at the start) is a valid value
    try:
        return await connector.create_event(
            title=event.title,
            start=event.start,
            end=event.end,
            all_day=event.all_day,
            calendar_url=target_url,
            **extras,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to create event: {exc}",
        )


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(event_id: int, current_user: User = Depends(require_min_role(ROLE_PARTNER)),
                       db: Session = Depends(get_db)):
    """Removes an event from the hub's family calendar (CalDAV events are managed in their calendar)."""
    from app.models.hub import HubEvent

    row = db.get(HubEvent, event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Termin nicht gefunden")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class EventUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    start: str
    end: str
    all_day: bool
    location: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=2000)
    recurrence: Literal["none", "daily", "weekly", "monthly", "yearly"] = "none"
    alarm_minutes: Optional[int] = Field(default=None, ge=0, le=10080)  # only applied when sent

    @model_validator(mode="after")
    def _times(self):
        try:
            start, end = _parse(self.start), _parse(self.end)
        except ValueError as exc:
            raise ValueError("Start und Ende als ISO-Datum angeben") from exc
        if end < start:
            raise ValueError("Ende liegt vor dem Start")
        return self


@router.put("/events/{event_id}")
async def update_event(event_id: int, data: EventUpdateRequest, current_user: User = Depends(require_min_role(ROLE_PARTNER)),
                       db: Session = Depends(get_db)):
    """Edits an event of the hub's family calendar (the whole series for repeating events)."""
    from app.models.hub import HubEvent

    row = db.get(HubEvent, event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Termin nicht gefunden")
    row.title, row.start, row.end, row.all_day = data.title.strip(), _parse(data.start), _parse(data.end), data.all_day
    row.location = (data.location or "").strip() or None
    row.notes = (data.notes or "").strip() or None
    row.recurrence = data.recurrence
    if "alarm_minutes" in data.model_fields_set:
        row.alarm_minutes = data.alarm_minutes
    db.commit()
    return _hub_event(row)


async def _own_calendar_url(db: Session, user: User, calendar_id: str) -> str:
    if not calendar_id.startswith("caldav:") or not (_caldav_active() and _user_account(db, user)):
        raise HTTPException(status_code=404, detail="Kalender nicht gefunden")
    match = [c for c in await connector_for_user(db, user).list_calendars() if c["id"] == calendar_id]
    if not match:
        raise HTTPException(status_code=404, detail="Kalender nicht gefunden")
    return match[0]["url"]


@router.put("/caldav/{calendar_id}/{uid}")
async def update_caldav_event(calendar_id: str, uid: str, data: EventUpdateRequest,
                              current_user: User = Depends(require_min_role(ROLE_PARTNER)), db: Session = Depends(get_db)):
    """Edits an event in one of the person's own CalDAV calendars. Series: title, place and notes only."""
    url = await _own_calendar_url(db, current_user, calendar_id)
    changes = {"title": data.title.strip(), "location": (data.location or "").strip(), "notes": (data.notes or "").strip(),
               "start": _parse(data.start).isoformat() if not data.all_day else _parse(data.start).date().isoformat(),
               "end": _parse(data.end).isoformat() if not data.all_day else _parse(data.end).date().isoformat(),
               "all_day": data.all_day}
    if "alarm_minutes" in data.model_fields_set:
        changes["alarm_minutes"] = data.alarm_minutes
    try:
        ok = await connector_for_user(db, current_user).update_event(url, uid, changes)
    except Exception as exc:  # noqa: BLE001
        logger.warning("CalDAV-Termin nicht geändert: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Kalender gerade nicht erreichbar") from exc
    if not ok:
        raise HTTPException(status_code=404, detail="Termin nicht gefunden")
    return {"updated": True}


@router.delete("/caldav/{calendar_id}/{uid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_caldav_event(calendar_id: str, uid: str, current_user: User = Depends(require_min_role(ROLE_PARTNER)),
                              db: Session = Depends(get_db)):
    url = await _own_calendar_url(db, current_user, calendar_id)
    try:
        ok = await connector_for_user(db, current_user).delete_event(url, uid)
    except Exception as exc:  # noqa: BLE001
        logger.warning("CalDAV-Termin nicht gelöscht: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Kalender gerade nicht erreichbar") from exc
    if not ok:
        raise HTTPException(status_code=404, detail="Termin nicht gefunden")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class ReminderSettings(BaseModel):
    calendar_on_phone: bool


@router.get("/me/reminders")
async def get_reminder_settings(current_user: User = Depends(get_current_user)):
    """Own setting: with the calendar synced on the phone, the phone alerts and the hub sends no event reminders."""
    return {"calendar_on_phone": bool(getattr(current_user, "calendar_on_phone", False))}


@router.put("/me/reminders")
async def put_reminder_settings(data: ReminderSettings, current_user: User = Depends(get_current_user),
                                db: Session = Depends(get_db)):
    user = db.get(User, current_user.id)
    user.calendar_on_phone = data.calendar_on_phone
    db.commit()
    return {"calendar_on_phone": user.calendar_on_phone}
