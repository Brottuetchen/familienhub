"""Zeit-Konvention: In der Datenbank liegen Zeitpunkte als UTC ohne Zeitzone.

Nach außen gehen sie immer mit „Z“. Eingaben ohne Zeitzone gelten als Ortszeit
(``TIMEZONE``, Standard Europe/Berlin). Kalenderlogik (z. B. „morgen 8 Uhr“,
Wiederholungen über die Zeitumstellung) rechnet in Ortszeit.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo


def local_tz() -> ZoneInfo:
    from app.config import settings

    return ZoneInfo(settings.timezone or "Europe/Berlin")


def to_utc_naive(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=local_tz())
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def utc_naive_to_local(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc).astimezone(local_tz())


def local_to_utc_naive(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def iso_z(dt: Optional[datetime]) -> Optional[str]:
    return None if dt is None else dt.replace(microsecond=0).isoformat() + "Z"


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
