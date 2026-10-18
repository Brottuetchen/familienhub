"""Calendar endpoints: the person's CalDAV calendars plus the hub's family calendar (``hub_calendar``)."""

from __future__ import annotations

from datetime import datetime, timedelta
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


class EventCreateRequest(BaseModel):
    """Neuen Kalendereintrag erstellen."""

    title: str = Field(min_length=1, max_length=200)
    start: str  # ISO 8601
    end: str  # ISO 8601
    all_day: bool
    calendar_url: Optional[str] = None
    # Target: the person's CalDAV calendar or the hub's family calendar. Default: CalDAV if set up, else hub.
    source: Optional[Literal["caldav", "hub"]] = None

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


def _hub_event(e) -> Dict[str, Any]:
    fmt = (lambda d: d.date().isoformat()) if e.all_day else (lambda d: d.isoformat())
    return {"id": e.id, "title": e.title, "start": fmt(e.start), "end": fmt(e.end), "all_day": bool(e.all_day),
            "location": e.location, "calendar": "Familie", "source": "hub"}


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
    if _hub_active():
        rows = db.query(HubEvent).filter(HubEvent.end >= start.replace(hour=0, minute=0, second=0, microsecond=0),
                                         HubEvent.start < end).all()
        events.extend(_hub_event(e) for e in rows)
    events.sort(key=lambda e: e.get("start") or "")
    return events


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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await collect_events(db, current_user, days)


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
    if event.source == "hub" or (event.source is None and not has_account and _hub_active()):
        if not _hub_active():
            raise HTTPException(status_code=409, detail="Der Familienkalender im Hub ist abgeschaltet")
        from app.models.hub import HubEvent

        row = HubEvent(title=event.title.strip(), start=_parse(event.start), end=_parse(event.end),
                       all_day=event.all_day, created_by=current_user.id)
        db.add(row)
        db.commit()
        return _hub_event(row)
    if not has_account:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "no_caldav_account"},
        )
    connector = connector_for_user(db, current_user)
    try:
        return await connector.create_event(
            title=event.title,
            start=event.start,
            end=event.end,
            all_day=event.all_day,
            calendar_url=event.calendar_url,
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
