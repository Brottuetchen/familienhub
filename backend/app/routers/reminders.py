"""Erinnerungen (Hermes-eigener Speicher)."""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_serializer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_reminder_action_token, get_current_user
from app.models.reminder import Reminder, visible_to
from app.models.service_key import ServiceKey
from app.models.user import User
from app.routers.notifications import service_key
from app.services.notify import notify
from app.core.timeutil import iso_z, local_tz, to_utc_naive, utcnow
from app.services.recurrence import VALID_RECURRENCE, advance_utc

router = APIRouter(prefix="/api/reminders", tags=["reminders"])

FireOn = Literal["time", "arrival"]


class ReminderRequest(BaseModel):
    title: str
    notes: Optional[str] = None
    due_at: Optional[datetime] = None
    priority: str = "info"
    recurrence: str = "none"
    family_member_id: Optional[int] = None
    for_family: bool = False
    fire_on: FireOn = "time"


class ReminderUpdate(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    due_at: Optional[datetime] = None
    priority: Optional[str] = None
    recurrence: Optional[str] = None
    completed: Optional[bool] = None
    for_family: Optional[bool] = None
    fire_on: Optional[FireOn] = None


class ReminderResponse(BaseModel):
    id: int
    title: str
    notes: Optional[str] = None
    due_at: Optional[datetime] = None
    priority: str
    recurrence: str
    completed: bool
    source: str
    for_family: bool = False
    fire_on: str = "time"
    created_by: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("due_at")
    def _due_utc(self, value: Optional[datetime]) -> Optional[str]:
        return iso_z(value)  # gespeichert als UTC → mit „Z“ ausgeben


def _validate_recurrence(value: Optional[str]) -> None:
    if value is not None and value not in VALID_RECURRENCE:
        raise HTTPException(status_code=400, detail=f"Invalid recurrence. Valid: {', '.join(sorted(VALID_RECURRENCE))}")


@router.get("", response_model=list[ReminderResponse])
async def list_reminders(include_completed: bool = False, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(Reminder).filter(visible_to(current_user.id))
    if not include_completed:
        query = query.filter(Reminder.completed == False)  # noqa: E712
    return query.order_by(Reminder.due_at.is_(None), Reminder.due_at.asc()).all()


def _family_allowed(user: User) -> bool:
    """Familien-Erinnerungen (für alle sichtbar) nur ab Partner; Kind und Gast nur eigene."""
    from app.core.security import ROLE_LEVEL
    from app.models.user import ROLE_PARTNER

    return user.is_admin or ROLE_LEVEL.get(user.role or ROLE_PARTNER, 0) >= ROLE_LEVEL[ROLE_PARTNER]


@router.post("", response_model=ReminderResponse)
async def create_reminder(data: ReminderRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _validate_recurrence(data.recurrence)
    if data.for_family and not _family_allowed(current_user):
        raise HTTPException(status_code=403, detail="Erinnerungen für die ganze Familie legen Erwachsene an")
    if data.fire_on == "arrival" and data.due_at is not None:
        raise HTTPException(status_code=400, detail="Erinnerung beim Heimkommen hat keine Uhrzeit")
    reminder = Reminder(
        title=data.title,
        notes=data.notes,
        due_at=to_utc_naive(data.due_at),
        priority=data.priority,
        recurrence=data.recurrence,
        family_member_id=data.family_member_id,
        for_family=data.for_family,
        fire_on=data.fire_on,
        source="user",
        created_by=current_user.id,
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return reminder


@router.patch("/{reminder_id}", response_model=ReminderResponse)
async def update_reminder(reminder_id: int, data: ReminderUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    reminder = db.query(Reminder).filter(Reminder.id == reminder_id, visible_to(current_user.id)).first()
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    _validate_recurrence(data.recurrence)

    updates = data.model_dump(exclude_unset=True)
    if (updates.get("for_family") or reminder.for_family) and not _family_allowed(current_user):
        raise HTTPException(status_code=403, detail="Erinnerungen für die ganze Familie ändern Erwachsene")
    if updates.get("fire_on") == "arrival":
        updates["due_at"] = None  # Zeit entfällt, Home Assistant meldet die Ankunft
    if "due_at" in updates:
        updates["due_at"] = to_utc_naive(updates["due_at"])
        reminder.notified = False
    if updates.get("completed") is True:
        updates.pop("completed")
        if "recurrence" in updates:
            reminder.recurrence = updates.pop("recurrence")
        apply_action(reminder, "done")
    for key, value in updates.items():
        setattr(reminder, key, value)
    db.commit()
    db.refresh(reminder)
    return reminder


ACTIONS = ("done", "snooze_1h", "tomorrow")


def apply_action(reminder: Reminder, action: str, minutes: Optional[int] = None) -> None:
    """Erledigt (wiederkehrend: nächster Termin), später erinnern oder auf morgen 8 Uhr legen."""
    from datetime import timedelta

    if action == "done" and reminder.fire_on == "arrival":
        if (reminder.recurrence or "none") != "none":
            # wiederkehrend: wieder scharf für die nächste Ankunft
            reminder.due_at, reminder.notified, reminder.completed = None, False, False
        else:
            reminder.completed = True
        return
    if action == "done":
        nxt = advance_utc(reminder.due_at, reminder.recurrence or "none")
        if nxt:
            reminder.due_at, reminder.notified, reminder.completed = nxt, False, False
        else:
            reminder.completed = True
        return
    if action == "snooze_1h" or action == "snooze":
        reminder.due_at = utcnow() + timedelta(minutes=minutes or 60)
    elif action == "tomorrow":
        now_local = datetime.now(local_tz())
        tomorrow8 = (now_local + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
        reminder.due_at = to_utc_naive(tomorrow8)
    else:
        raise HTTPException(status_code=400, detail=f"Unbekannte Aktion. Erlaubt: {', '.join(ACTIONS)}")
    reminder.notified = False
    reminder.completed = False


class SnoozeRequest(BaseModel):
    minutes: int = Field(60, ge=5, le=60 * 24 * 7)


@router.post("/{reminder_id}/snooze", response_model=ReminderResponse)
async def snooze(reminder_id: int, data: SnoozeRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    reminder = db.query(Reminder).filter(Reminder.id == reminder_id, visible_to(current_user.id)).first()
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    apply_action(reminder, "snooze", minutes=data.minutes)
    db.commit()
    db.refresh(reminder)
    return reminder


class ActionRequest(BaseModel):
    action: str
    token: str


@router.post("/{reminder_id}/action", response_model=ReminderResponse)
async def action_from_notification(reminder_id: int, data: ActionRequest, db: Session = Depends(get_db)):
    """Knopf in der Mitteilung (ohne Anmeldung; Service Worker/Android-Hintergrund).

    Berechtigt durch das signierte Aktions-Token aus der Mitteilung: gilt nur für diese
    Erinnerung und diese Person, kurz gültig.
    """
    from app.core.security import verify_reminder_action_token

    claims = verify_reminder_action_token(data.token)
    if not claims or claims.get("rid") != reminder_id:
        raise HTTPException(status_code=401, detail="Aktion abgelaufen oder ungültig")
    reminder = db.query(Reminder).filter(Reminder.id == reminder_id, visible_to(claims["uid"])).first()
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    if data.action not in ACTIONS:
        raise HTTPException(status_code=400, detail=f"Unbekannte Aktion. Erlaubt: {', '.join(ACTIONS)}")
    apply_action(reminder, data.action)
    db.commit()
    db.refresh(reminder)
    return reminder


class ArrivedIn(BaseModel):
    user: str = Field(min_length=1, max_length=100)  # Hub-Benutzername


@router.post("/arrived")
async def arrived(data: ArrivedIn, key: ServiceKey = Depends(service_key), db: Session = Depends(get_db)):
    """Jemand ist nach Hause gekommen (Home Assistant, Dienst-Schlüssel).

    Löst die offenen Ankunfts-Erinnerungen dieser Person aus. Familien-Erinnerungen bekommt,
    wer zuerst heimkommt; danach sind sie verbraucht.
    """
    user = db.query(User).filter(User.is_active == True).all()  # noqa: E712
    person = next((u for u in user if u.username.lower() == data.user.strip().lower()), None)
    if not person:
        raise HTTPException(status_code=404, detail="Unbekannte Person")
    pending: List[Reminder] = (
        db.query(Reminder)
        .filter(
            Reminder.fire_on == "arrival",
            Reminder.completed == False,  # noqa: E712
            Reminder.notified == False,  # noqa: E712
            visible_to(person.id),
        )
        .order_by(Reminder.id)
        .all()
    )
    for reminder in pending:
        await notify(
            person.id,
            "🏠 Willkommen zu Hause",
            reminder.title,
            data={
                "route": "/reminders",
                "reminder_id": reminder.id,
                "actions": "done,snooze_1h",
                "action_token": create_reminder_action_token(reminder.id, person.id),
            },
            category="reminder",
            source=key.name,
        )
        reminder.notified = True
    db.commit()
    return {"fired": [r.title for r in pending]}


@router.delete("/{reminder_id}")
async def delete_reminder(reminder_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    reminder = db.query(Reminder).filter(Reminder.id == reminder_id, visible_to(current_user.id)).first()
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    if reminder.for_family and not _family_allowed(current_user):
        raise HTTPException(status_code=403, detail="Erinnerungen für die ganze Familie löschen Erwachsene")
    db.delete(reminder)
    db.commit()
    return {"message": "deleted"}
