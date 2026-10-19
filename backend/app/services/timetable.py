"""Timetable of children: A/B weeks, school holidays from a calendar subscription, the "Today" summary.

Settings live in ``config_overrides`` (like the family Today layout):
- ``TIMETABLE_AB_REFERENCE``: any date inside a week that counts as an "A" week (empty = no A/B weeks)
- ``TIMETABLE_HOLIDAY_FEED``: id of a calendar subscription (``ICS_FEEDS``, e.g. ``ics:schule``) whose events
  mark school holidays; lessons (kind ``school``) are hidden on those days. Sports, music and clubs stay.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.services import timetable_plugin
from app.models.config import ConfigOverride
from app.models.timetable import TimetableEntry
from app.models.user import ROLE_CHILD, User

logger = get_logger("service.timetable")

AB_KEY = "TIMETABLE_AB_REFERENCE"
FEED_KEY = "TIMETABLE_HOLIDAY_FEED"


def _get(db: Session, key: str) -> Optional[str]:
    row = db.get(ConfigOverride, key)
    return row.value if row and row.value else None


def _put(db: Session, key: str, value: Optional[str]) -> None:
    row = db.get(ConfigOverride, key)
    if not value:
        if row is not None:
            db.delete(row)
        return
    row = row or ConfigOverride(key=key)
    row.value, row.secret = value, False
    db.add(row)


def get_settings(db: Session) -> Dict[str, Optional[str]]:
    return {"ab_reference": _get(db, AB_KEY), "holiday_feed": _get(db, FEED_KEY)}


def save_settings(db: Session, ab_reference: Optional[date], holiday_feed: Optional[str]) -> None:
    _put(db, AB_KEY, ab_reference.isoformat() if ab_reference else None)
    _put(db, FEED_KEY, holiday_feed)
    db.commit()


def available_feeds() -> List[Dict[str, str]]:
    from app.plugins.base import get_setting
    from app.services.ics import feed_id, parse_feeds

    return [{"id": feed_id(name), "name": name} for name, _ in parse_feeds(get_setting("ICS_FEEDS"))]


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def week_variant(db: Session, day: date) -> Optional[str]:
    """'a' or 'b' for the week of ``day``; None without a configured reference week."""
    ref = _get(db, AB_KEY)
    try:
        ref_day = date.fromisoformat(ref) if ref else None
    except ValueError:
        ref_day = None
    if ref_day is None:
        return None
    return "a" if ((_monday(day) - _monday(ref_day)).days // 7) % 2 == 0 else "b"


def is_parent(user: User) -> bool:
    return bool(user.is_admin or user.role in ("admin", "partner"))


def children_visible_to(db: Session, user: User) -> List[User]:
    """Parents (partner/admin) see every child, a child only themselves, everyone else nobody."""
    if is_parent(user):
        return db.query(User).filter(User.role == ROLE_CHILD, User.is_active.is_(True)).order_by(User.id).all()
    if user.role == ROLE_CHILD:
        return [user]
    return []


async def holidays(db: Session, start: date, end: date) -> List[Dict[str, Any]]:
    """School-holiday periods (inclusive dates) from the chosen subscription; empty if unset or unreachable."""
    feed = _get(db, FEED_KEY)
    if not feed:
        return []
    try:
        from app.services import ics

        events = await ics.events_between(datetime.combine(start, datetime.min.time()),
                                          datetime.combine(end + timedelta(days=1), datetime.min.time()))
    except Exception as exc:  # noqa: BLE001 - fail softly: no holiday info, lessons are shown
        logger.warning("School holidays not readable: %s", type(exc).__name__)
        return []
    out = []
    for e in events:
        if e.get("calendar_id") != feed:
            continue
        try:
            first = datetime.fromisoformat(e["start"]).date()
            last_raw = datetime.fromisoformat(e["end"])
        except (ValueError, KeyError):
            continue
        # End dates of all-day events (and timed ones ending at midnight) are exclusive
        exclusive = (e.get("all_day") or last_raw.time() == datetime.min.time()) and last_raw.date() > first
        last = last_raw.date() - timedelta(days=1) if exclusive else last_raw.date()
        out.append({"start": first.isoformat(), "end": last.isoformat(), "title": e.get("title") or ""})
    out.sort(key=lambda h: h["start"])
    return out


def holiday_on(periods: List[Dict[str, Any]], day: date) -> Optional[str]:
    for h in periods:
        if h["start"] <= day.isoformat() <= h["end"]:
            return h["title"] or "-"
    return None


def serialize(e: TimetableEntry) -> Dict[str, Any]:
    return {"id": e.id, "child_id": e.child_id, "weekday": e.weekday, "week": e.week, "start": e.start, "end": e.end,
            "title": e.title, "kind": e.kind, "location": e.location}


def entries_on(db: Session, child_id: int, day: date, periods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """What the child has on ``day``: weekday + matching week variant; lessons drop out on holidays."""
    variant = week_variant(db, day)
    weeks = ["all"] + ([variant] if variant else [])
    rows = (db.query(TimetableEntry)
            .filter(TimetableEntry.child_id == child_id, TimetableEntry.weekday == day.weekday(),
                    TimetableEntry.week.in_(weeks)).order_by(TimetableEntry.start, TimetableEntry.id).all())
    on_holiday = holiday_on(periods, day) is not None
    return [serialize(r) for r in rows if not (on_holiday and r.kind == "school")]


async def today_card(db: Session, user: User, day: date) -> Dict[str, Any]:
    """Data of the Today card: own day for a child, all children for parents. Never raises.

    Lessons from a plugin replace the manual school entries of the day (cancelled ones stay in the list with their
    status, so the card can say "1st-2nd period cancelled")."""
    try:
        kids = children_visible_to(db, user)
        periods = await holidays(db, day, day) if kids else []
        holiday = holiday_on(periods, day)
        plugin_lessons = await timetable_plugin.lessons_for_children(db, kids, day, day) if kids else {}
        out = []
        for kid in kids:
            by_day, _ = plugin_lessons.get(kid.id, ({}, "none"))
            lessons, source = timetable_plugin.merge_day(kid.id, day, entries_on(db, kid.id, day, periods),
                                                         by_day.get(day.isoformat()))
            kid_holiday = holiday if source == "manual" else None  # a plugin that has lessons knows better
            if lessons or kid_holiday:
                out.append({"child_id": kid.id, "name": kid.effective_name, "holiday": kid_holiday, "source": source,
                            "entries": lessons})
        return {"status": "ok", "date": day.isoformat(), "week": week_variant(db, day), "children": out}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Timetable for Today failed: %s", exc, exc_info=True)
        return {"status": "unavailable", "date": day.isoformat(), "week": None, "children": []}


async def week_view(db: Session, kid: User, any_day: date) -> Dict[str, Any]:
    """The seven days (Monday first) of the week of ``any_day``, manual entries merged with the plugin's lessons."""
    first, last = timetable_plugin.week_bounds(any_day)
    periods = await holidays(db, first, last)
    by_day, status = await timetable_plugin.lessons(db, kid, first, last)
    row = timetable_plugin.source_of(db, kid.id)
    days = []
    for i in range(7):
        day = first + timedelta(days=i)
        entries, source = timetable_plugin.merge_day(kid.id, day, entries_on(db, kid.id, day, periods),
                                                     by_day.get(day.isoformat()))
        days.append({"date": day.isoformat(), "weekday": i, "source": source,
                     "holiday": holiday_on(periods, day) if source == "manual" else None, "entries": entries})
    return {"child": {"id": kid.id, "name": kid.effective_name}, "start": first.isoformat(), "end": last.isoformat(),
            "week": week_variant(db, first), "plugin": plugin_info(row, status), "days": days}


def plugin_info(row, status: str) -> Optional[Dict[str, Any]]:
    """Which plugin provides the lessons of a child (None without a mapping) and how it answered."""
    if row is None:
        return None
    from app.plugins.registry import plugin_registry

    plugin = plugin_registry.get(row.plugin_id)
    return {"id": row.plugin_id, "name": plugin.name if plugin else row.plugin_id, "person": row.person_name or row.person_id,
            "status": status}


def _clone(e: TimetableEntry, weekday: int, week: str) -> TimetableEntry:
    return TimetableEntry(child_id=e.child_id, weekday=weekday, week=week, start=e.start, end=e.end,
                          title=e.title, kind=e.kind, location=e.location)


def copy_day(db: Session, child_id: int, week: str, from_weekday: int, to_weekdays: List[int],
             to_week: Optional[str] = None) -> int:
    """Replaces the target days (in ``to_week``, default the same variant) with copies of one day."""
    to_week = to_week or week
    src = db.query(TimetableEntry).filter_by(child_id=child_id, weekday=from_weekday, week=week).all()
    count = 0
    for wd in sorted(set(to_weekdays)):
        if wd == from_weekday and to_week == week:
            continue
        db.query(TimetableEntry).filter_by(child_id=child_id, weekday=wd, week=to_week).delete()
        for e in src:
            db.add(_clone(e, wd, to_week))
            count += 1
    db.commit()
    return count


def copy_week(db: Session, child_id: int, from_week: str, to_week: str) -> int:
    """Replaces the whole ``to_week`` variant with a copy of ``from_week``."""
    src = db.query(TimetableEntry).filter_by(child_id=child_id, week=from_week).all()
    db.query(TimetableEntry).filter_by(child_id=child_id, week=to_week).delete()
    for e in src:
        db.add(_clone(e, e.weekday, to_week))
    db.commit()
    return len(src)
