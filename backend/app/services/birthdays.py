"""Birthdays and anniversaries: yearly occurrences, ages, calendar events and reminder notifications.

- Entries repeat every year; the year of birth/wedding is optional (without it no age is shown).
- 29 February: in years without one the day is celebrated on 28 February (never skipped).
- Gift ideas are never part of anything computed here (calendar, Today, notifications): only the
  dedicated gift endpoints expose them, and those hide them from the person the entry is linked to.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from app.core.logging_config import get_logger
from app.core.timeutil import local_tz

logger = get_logger("service.birthdays")

KINDS = ("birthday", "anniversary")
ICON = {"birthday": "🎂", "anniversary": "💍"}
REMIND_AT_HOUR = 8  # local time from which advance notices go out
CALENDAR_ID = "birthdays"
CALENDAR_NAME = "Geburtstage"


def valid_date(month: int, day: int, year: Optional[int] = None) -> bool:
    """29 February is valid without a year and for leap years only when a year is given."""
    if not 1 <= month <= 12 or day < 1:
        return False
    if year is not None and not 1 <= year <= 9999:
        return False
    if month == 2 and day == 29 and year is not None:
        return calendar.isleap(year)
    return day <= calendar.monthrange(2000, month)[1]  # 2000 is a leap year


def occurrence_in(year: int, month: int, day: int) -> date:
    """The day in ``year``; 29 February falls back to 28 February in non-leap years."""
    if month == 2 and day == 29 and not calendar.isleap(year):
        return date(year, 2, 28)
    return date(year, month, day)


def next_occurrence(month: int, day: int, ref: date) -> date:
    """First occurrence on or after ``ref``."""
    this = occurrence_in(ref.year, month, day)
    return this if this >= ref else occurrence_in(ref.year + 1, month, day)


def age_on(year: Optional[int], occurrence: date) -> Optional[int]:
    """Age / years at the given occurrence; None when the year is unknown."""
    if year is None:
        return None
    n = occurrence.year - year
    return n if n >= 0 else None


def describe(row: Any, ref: date) -> Dict[str, Any]:
    nxt = next_occurrence(row.month, row.day, ref)
    return {"next_date": nxt.isoformat(), "days_until": (nxt - ref).days, "turns": age_on(row.year, nxt)}


def display_title(row: Any, occurrence: date) -> str:
    age = age_on(row.year, occurrence)
    base = f"{ICON.get(row.kind, '🎂')} {row.name}"
    return f"{base} ({age})" if age else base


def calendar_events(rows: List[Any], start: date, end: date) -> List[Dict[str, Any]]:
    """Read-only all-day events for every occurrence with ``start <= day < end``."""
    out: List[Dict[str, Any]] = []
    for row in rows:
        for year in range(start.year, end.year + 1):
            day = occurrence_in(year, row.month, row.day)
            if start <= day < end:
                out.append({
                    "id": f"birthday-{row.id}-{day.isoformat()}", "title": display_title(row, day),
                    "start": day.isoformat(), "end": (day + timedelta(days=1)).isoformat(), "all_day": True,
                    "location": None, "notes": None, "recurrence": "yearly", "alarm_minutes": None,
                    "calendar": CALENDAR_NAME, "calendar_id": CALENDAR_ID, "source": "birthdays",
                    "birthday_id": row.id,
                })
    return out


def can_view(user: Any) -> bool:
    """Guests are outside the family: they see no birthdays (nor reminders)."""
    from app.models.user import ROLE_GUEST

    return bool(user.is_admin) or (user.role or "") != ROLE_GUEST


def visible_rows(db, user: Any) -> List[Any]:
    from app.models.birthday import Birthday

    if not can_view(user):
        return []
    return db.query(Birthday).order_by(Birthday.month, Birthday.day, Birthday.name).all()


def upcoming(db, user: Any, ref: date, days: int = 30, limit: int = 5) -> List[Dict[str, Any]]:
    """Entries within the next ``days`` days for Today, nearest first."""
    out = []
    for row in visible_rows(db, user):
        info = describe(row, ref)
        if info["days_until"] <= days:
            out.append({"id": row.id, "name": row.name, "kind": row.kind, **info, "is_you": row.user_id == user.id})
    out.sort(key=lambda b: (b["days_until"], b["name"].lower()))
    return out[:limit]


# --- reminders ---------------------------------------------------------------------------------------------------


def message(row: Any, occurrence: date, days: int) -> tuple:
    """Title and body (German; translated per recipient by notify())."""
    age = age_on(row.year, occurrence)
    title = f"{ICON.get(row.kind, '🎂')} {row.name}"
    noun = "Geburtstag" if row.kind == "birthday" else "Jahrestag"
    if days == 0:
        body = f"{noun} heute"
    elif days == 1:
        body = f"{noun} morgen"
    else:
        body = f"{noun} in {days} Tagen"
    if age:
        body += f" · wird {age}" if row.kind == "birthday" else f" · {age}. Jahrestag"
    return title, body


async def send_due(now: Optional[datetime] = None) -> int:
    """Scheduler step: once per person and occurrence, ``remind_days_before`` days ahead (from 08:00 local time).

    The linked person is not told in advance about their own birthday. Guests get nothing.
    """
    from app.core.database import SessionLocal
    from app.models.birthday import Birthday
    from app.models.event_alarm import EventAlarmSent
    from app.models.user import User
    from app.services.notify import notify

    local = now or datetime.now(local_tz()).replace(tzinfo=None)
    if local.hour < REMIND_AT_HOUR:
        return 0
    today = local.date()
    sent = 0
    with SessionLocal() as db:
        rows = db.query(Birthday).filter(Birthday.remind_days_before.isnot(None)).all()
        users = None
        for row in rows:
            nxt = next_occurrence(row.month, row.day, today)
            days = (nxt - today).days
            if days != row.remind_days_before:
                continue
            if users is None:
                users = [u for u in db.query(User).filter(User.is_active == True).all() if can_view(u)]  # noqa: E712
            for user in users:
                if user.id == row.user_id:
                    continue
                key = f"birthday|{row.id}|{nxt.isoformat()}|{days}"
                if db.query(EventAlarmSent).filter_by(user_id=user.id, key=key).first():
                    continue
                db.add(EventAlarmSent(user_id=user.id, key=key, sent_at=datetime.utcnow()))
                db.commit()
                title, body = message(row, nxt, days)
                try:
                    await notify(user.id, title, body, data={"route": "/birthdays"}, category="reminder")
                    sent += 1
                except Exception as exc:  # noqa: BLE001 - one person's delivery must not stop the others
                    logger.warning("birthday notice for user %s failed: %s", user.id, type(exc).__name__)
    return sent
