"""Event reminders: alarms written into events and hub notifications before events.

- An event's reminder is stored as a VALARM in CalDAV events (so phones that sync the calendar alert by
  themselves) and as ``alarm_minutes`` in hub events.
- For people whose calendar is not set up on their phone (``users.calendar_on_phone`` false, the default),
  the scheduler sends a hub notification when an alarm is due. Events without an alarm (holidays,
  subscriptions) never notify.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.core.logging_config import get_logger
from app.core.timeutil import local_tz

logger = get_logger("service.event_alarms")

CHOICES = (0, 5, 15, 30, 60, 1440)  # minutes before the start the app offers; 0 = at the start
DEFAULT = 15
LATE_GRACE = timedelta(minutes=10)  # a missed tick (restart) still notifies up to 10 minutes late


# --- iCalendar ---------------------------------------------------------------------------------------------------


def set_alarm(component: Any, minutes: Optional[int], title: str) -> None:
    """Replace the event's alarms with one ``minutes`` before the start (None: no alarm)."""
    from icalendar import Alarm

    component.subcomponents = [c for c in component.subcomponents if getattr(c, "name", "") != "VALARM"]
    if minutes is None:
        return
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("description", title or "Termin")
    alarm.add("trigger", timedelta(minutes=-int(minutes)))
    component.add_component(alarm)


def alarm_minutes(component: Any) -> Optional[int]:
    """Minutes before the start of the event's first alarm, or None. Absolute triggers count against DTSTART."""
    for sub in getattr(component, "subcomponents", []) or []:
        if getattr(sub, "name", "") != "VALARM":
            continue
        trigger = sub.get("trigger")
        value = getattr(trigger, "dt", None)
        if isinstance(value, timedelta):
            related = str(getattr(trigger, "params", {}).get("RELATED", "START")).upper()
            if related == "END":
                continue  # alarms relative to the end are rare; not offered by the app
            return max(0, int(round(-value.total_seconds() / 60)))
        if isinstance(value, datetime):
            start = getattr(component.get("dtstart"), "dt", None)
            begin = _as_local(start)
            if begin is not None:
                return max(0, int(round((begin - _as_local(value)).total_seconds() / 60)))
    return None


# --- due alarms --------------------------------------------------------------------------------------------------


def _as_local(value: Any) -> Optional[datetime]:
    """Naive local wall time for a date, an aware or a naive (already local) datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(local_tz()).replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    return None


def _parse_start(value: Any) -> Optional[datetime]:
    if isinstance(value, (datetime, date)):
        return _as_local(value)
    try:
        text = str(value)
        if len(text) == 10:
            return _as_local(date.fromisoformat(text))
        return _as_local(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        return None


def due(events: Iterable[Dict[str, Any]], now: datetime) -> List[Tuple[str, datetime, Dict[str, Any]]]:
    """(key, fire time, event) for alarms due in (now - LATE_GRACE, now]. ``now`` is naive local time."""
    out = []
    for event in events:
        minutes = event.get("alarm_minutes")
        if minutes is None:
            continue
        start = _parse_start(event.get("start"))
        if start is None:
            continue
        fire = start - timedelta(minutes=int(minutes))
        if now - LATE_GRACE < fire <= now:
            ident = event.get("uid") or event.get("id") or event.get("title")
            key = f"{event.get('calendar_id') or event.get('source') or ''}|{ident}|{start.isoformat()}|{minutes}"
            out.append((key[:300], fire, event))
    return out


def message(event: Dict[str, Any], now: datetime) -> Tuple[str, str]:
    """Title and body of the notification (German; translated per recipient by notify())."""
    title = f"📅 {event.get('title') or 'Termin'}"
    start = _parse_start(event.get("start"))
    cal = event.get("calendar") or ""
    if event.get("all_day") or start is None:
        when = "Heute" if start is None or start.date() <= now.date() else "Morgen"
    else:
        clock = start.strftime("%H:%M")
        when = f"Um {clock} Uhr" if start.date() == now.date() else f"Morgen um {clock} Uhr"
    return title, f"{when} · {cal}" if cal else when


async def send_due(now_utc: Optional[datetime] = None) -> int:
    """Scheduler step: notify everyone without the calendar on their phone about due alarms (once each)."""
    from app.core.database import SessionLocal
    from app.models.event_alarm import EventAlarmSent
    from app.models.user import User
    from app.routers.calendar import collect_events
    from app.services.notify import notify

    now = datetime.now(local_tz()).replace(tzinfo=None) if now_utc is None else _as_local(now_utc)
    sent = 0
    with SessionLocal() as db:
        users = db.query(User).filter(User.is_active == True).all()  # noqa: E712
        for user in users:
            if getattr(user, "calendar_on_phone", False):
                continue
            try:
                # the alarm window reaches one day ahead ("1 day before"), the start must not be over yet
                events = await collect_events(db, user, days=2, start=now - timedelta(hours=1))
            except Exception as exc:  # noqa: BLE001 - one person's calendar must not stop the others
                logger.warning("event alarms for user %s skipped: %s", user.id, type(exc).__name__)
                continue
            for key, _fire, event in due(events, now):
                if db.query(EventAlarmSent).filter_by(user_id=user.id, key=key).first():
                    continue
                db.add(EventAlarmSent(user_id=user.id, key=key, sent_at=datetime.utcnow()))
                db.commit()
                title, body = message(event, now)
                await notify(user.id, title, body, data={"route": "/calendar"}, category="reminder")
                sent += 1
        cutoff = datetime.utcnow() - timedelta(days=3)
        db.query(EventAlarmSent).filter(EventAlarmSent.sent_at < cutoff).delete()
        db.commit()
    return sent
