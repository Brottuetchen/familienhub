"""Wiederholungslogik für Erinnerungen.

Unterstützte Muster: none | daily | weekdays (Mo–Fr) | weekly | monthly.
"""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta
from typing import Optional

VALID_RECURRENCE = {"none", "daily", "weekdays", "weekly", "monthly"}

# Deutsche Wochentage -> weekday()-Index (Montag=0).
WEEKDAYS_DE = {
    "montag": 0,
    "dienstag": 1,
    "mittwoch": 2,
    "donnerstag": 3,
    "freitag": 4,
    "samstag": 5,
    "sonnabend": 5,
    "sonntag": 6,
}


def _add_month(dt: datetime) -> datetime:
    month = dt.month + 1
    year = dt.year
    if month > 12:
        month = 1
        year += 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def advance_utc(due_at_utc: Optional[datetime], recurrence: str) -> Optional[datetime]:
    """Nächste Fälligkeit für in UTC gespeicherte Zeitpunkte.

    Gerechnet wird in Ortszeit: „wöchentlich 9 Uhr“ bleibt 9 Uhr über die Zeitumstellung.
    """
    from app.core.timeutil import local_to_utc_naive, local_tz, utc_naive_to_local

    if not due_at_utc or recurrence in (None, "none"):
        return None
    local = utc_naive_to_local(due_at_utc).replace(tzinfo=None)
    nxt = advance(local, recurrence)
    return local_to_utc_naive(nxt.replace(tzinfo=local_tz())) if nxt else None


def advance(due_at: Optional[datetime], recurrence: str) -> Optional[datetime]:
    """Berechnet den nächsten Fälligkeitszeitpunkt (Wanduhrzeit) für ein Wiederholungsmuster."""
    if not due_at or recurrence in (None, "none"):
        return None
    if recurrence == "daily":
        return due_at + timedelta(days=1)
    if recurrence == "weekly":
        return due_at + timedelta(days=7)
    if recurrence == "weekdays":
        nxt = due_at + timedelta(days=1)
        while nxt.weekday() >= 5:  # Sa/So überspringen
            nxt += timedelta(days=1)
        return nxt
    if recurrence == "monthly":
        return _add_month(due_at)
    return None


def next_weekday(weekday_idx: int, hour: int = 9, minute: int = 0, ref: Optional[datetime] = None) -> datetime:
    """Nächstes Auftreten eines Wochentags zur angegebenen Uhrzeit."""
    ref = ref or datetime.now()
    days_ahead = (weekday_idx - ref.weekday()) % 7
    candidate = (ref + timedelta(days=days_ahead)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )
    if candidate <= ref:
        candidate += timedelta(days=7)
    return candidate


def next_at(hour: int = 9, minute: int = 0, ref: Optional[datetime] = None) -> datetime:
    """Heute zur Uhrzeit – oder morgen, falls schon vorbei."""
    ref = ref or datetime.now()
    candidate = ref.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= ref:
        candidate += timedelta(days=1)
    return candidate


def label(recurrence: str) -> str:
    return {
        "daily": "täglich",
        "weekdays": "werktags",
        "weekly": "wöchentlich",
        "monthly": "monatlich",
    }.get(recurrence, "")
