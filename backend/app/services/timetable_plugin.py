"""Lessons from plugins (capability ``timetable``) and how they merge with the manually entered timetable.

A parent maps each child to a plugin and to the person's identifier in the plugin's system (table
``timetable_sources``). For every day the plugin returns lessons for, those replace the child's manual ``school``
entries; manual sports, music and clubs stay. A day the plugin returns nothing for (holidays, weekend, plugin down)
shows the manual entries as before.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models.timetable import TimetableSource
from app.models.user import User
from app.plugins.sources import PluginSourceError, overrides, safe_call

logger = get_logger("service.timetable.plugin")

# Inside the 4 s budget of the Today card
PLUGIN_TIMEOUT = 3.0
CACHE_TTL = 60.0
STATUSES = ("normal", "cancelled", "substitution", "changed")
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
KINDS = ("school", "sport", "music", "club", "other")


@dataclass(frozen=True)
class ChildRef:
    """What a plugin gets for ``Plugin.timetable``: the hub child and who it is in the plugin's system."""

    id: int
    name: str
    person_id: str


_cache: Dict[Tuple[Any, ...], Tuple[float, Dict[str, List[Dict[str, Any]]]]] = {}


def clear_cache() -> None:
    _cache.clear()


def timetable_plugins() -> List[Any]:
    """Active plugins with capability ``timetable`` that implement the hook."""
    from app.plugins.registry import plugin_registry

    return [p for p in plugin_registry.all() if "timetable" in p.capabilities and p.active and overrides(p, "timetable")]


def source_of(db: Session, child_id: int) -> Optional[TimetableSource]:
    return db.get(TimetableSource, child_id)


def _lesson(raw: Any, first: date, last: date) -> Optional[Dict[str, Any]]:
    """One lesson as the plugin returned it -> clean dict, or None when unusable."""
    if not isinstance(raw, dict):
        return None
    try:
        day = date.fromisoformat(str(raw.get("date"))[:10])
    except ValueError:
        return None
    start, end, title = str(raw.get("start") or ""), str(raw.get("end") or ""), str(raw.get("title") or "").strip()
    if not (first <= day <= last) or not _TIME.match(start) or not _TIME.match(end) or not title or end < start:
        return None
    kind = str(raw.get("kind") or "school").lower()
    status = str(raw.get("status") or "normal").lower()
    period = raw.get("period")
    out = {"date": day.isoformat(), "weekday": day.weekday(), "start": start, "end": end, "title": title[:80],
           "kind": kind if kind in KINDS else "other", "status": status if status in STATUSES else "normal",
           "location": (str(raw["location"])[:80] if raw.get("location") else None),
           "note": (str(raw["note"])[:200] if raw.get("note") else None),
           "teacher": (str(raw["teacher"])[:80] if raw.get("teacher") else None),
           "period": period if isinstance(period, int) and not isinstance(period, bool) and 0 < period < 30 else None}
    return out


async def lessons(db: Session, child: User, first: date, last: date) -> Tuple[Dict[str, List[Dict[str, Any]]], str]:
    """Lessons of the child from the mapped plugin by ISO day, and a status: ``none`` (no plugin mapped), ``ok`` or
    ``unavailable``. Never raises."""
    row = source_of(db, child.id)
    if row is None:
        return {}, "none"
    plugin = next((p for p in timetable_plugins() if p.id == row.plugin_id), None)
    if plugin is None:
        return {}, "unavailable"  # plugin removed, switched off or not set up
    key = (plugin.id, row.person_id, first, last)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL:
        return hit[1], "ok"
    ref = ChildRef(child.id, child.effective_name, row.person_id)
    try:
        raw = await safe_call(plugin.id, "timetable", plugin.timetable(ref, first, last, db), PLUGIN_TIMEOUT)
        if not isinstance(raw, (list, tuple)):
            raise PluginSourceError("not a list")
    except PluginSourceError:
        return {}, "unavailable"
    by_day: Dict[str, List[Dict[str, Any]]] = {}
    for item in raw:
        clean = _lesson(item, first, last)
        if clean:
            by_day.setdefault(clean["date"], []).append(clean)
    for day_lessons in by_day.values():
        day_lessons.sort(key=lambda x: (x["start"], x["end"], x["title"]))
    if len(_cache) > 200:
        _cache.clear()
    _cache[key] = (time.monotonic(), by_day)
    return by_day, "ok"


async def lessons_for_children(db: Session, kids: List[User], first: date, last: date) -> Dict[int, Tuple[Dict[str, List[Dict[str, Any]]], str]]:
    """``lessons`` for several children at once (the plugins are called concurrently)."""
    results = await asyncio.gather(*(lessons(db, k, first, last) for k in kids))
    return {k.id: r for k, r in zip(kids, results)}


def plugin_entry(child_id: int, lesson: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": 0, "child_id": child_id, "week": "all", "source": "plugin", **lesson}


def manual_entry(entry: Dict[str, Any], day: date) -> Dict[str, Any]:
    return {**entry, "date": day.isoformat(), "status": "normal", "note": None, "teacher": None, "period": None,
            "source": "manual"}


def merge_day(child_id: int, day: date, manual: List[Dict[str, Any]],
              plugin_day: Optional[List[Dict[str, Any]]]) -> Tuple[List[Dict[str, Any]], str]:
    """One day of one child: ``(entries, source)``. ``manual`` are the (holiday-filtered) manual entries."""
    entries = [manual_entry(e, day) for e in manual]
    if not plugin_day:
        return entries, "manual"
    merged = [plugin_entry(child_id, x) for x in plugin_day] + [e for e in entries if e["kind"] != "school"]
    merged.sort(key=lambda e: (e["start"], e["end"]))
    return merged, "plugin"


# --- mapping children to plugin people ---------------------------------------------------------------------------


async def people(plugin: Any) -> Tuple[List[Dict[str, str]], bool]:
    """People of the plugin's system ``[{id, name}]`` and whether the answer can be trusted (hook implemented and
    reachable). Never raises."""
    if not overrides(plugin, "timetable_people"):
        return [], False
    try:
        raw = await safe_call(plugin.id, "timetable people", plugin.timetable_people(), PLUGIN_TIMEOUT * 2)
    except PluginSourceError:
        return [], False
    if not isinstance(raw, (list, tuple)):
        return [], False
    out = []
    for p in raw:
        if isinstance(p, dict) and p.get("id") not in (None, "") and str(p.get("name") or p["id"]).strip():
            out.append({"id": str(p["id"])[:200], "name": str(p.get("name") or p["id"]).strip()[:120]})
    return out, True


def save_source(db: Session, child_id: int, plugin_id: Optional[str], person_id: Optional[str],
                person_name: Optional[str]) -> None:
    row = db.get(TimetableSource, child_id)
    if not plugin_id or not person_id:
        if row is not None:
            db.delete(row)
        return
    if row is None:
        row = TimetableSource(child_id=child_id, plugin_id=plugin_id, person_id=person_id)
        db.add(row)
    row.plugin_id, row.person_id, row.person_name = plugin_id, person_id, person_name
    row.updated_at = datetime.utcnow()


def week_bounds(day: date) -> Tuple[date, date]:
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)
