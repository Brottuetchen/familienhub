"""Kalender-Endpunkte (CalDAV/Nextcloud)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.connectors.registry import registry
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.caldav import CalDAVAccount
from app.models.user import User
from app.services.holidays import upcoming_holidays

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


class EventCreateRequest(BaseModel):
    """Neuen Kalendereintrag erstellen."""

    title: str
    start: str  # ISO 8601
    end: str  # ISO 8601
    all_day: bool
    calendar_url: Optional[str] = None


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
    return await connector_for_user(db, current_user).get_events(days_ahead=days)


@router.get("/holidays")
async def holidays(days: int = 60, current_user: User = Depends(get_current_user)):
    """Deutsche Feiertage (bundesweit) in den nächsten Tagen."""
    return upcoming_holidays(days=days)


@router.post("/events", status_code=status.HTTP_201_CREATED)
async def create_event(
    event: EventCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Erstellt einen Termin per CalDAV mit dem Konto des Nutzers.

    Ohne CalDAV-Konto → 409 no_caldav_account. Der globale Kalenderzugang wird
    bewusst nicht verwendet, damit Termine dem richtigen Nutzer gehören.
    """
    if not _user_account(db, current_user):
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
