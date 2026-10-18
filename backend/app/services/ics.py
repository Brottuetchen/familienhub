"""Calendar subscriptions (ICS feeds) for the family calendar, read-only. Feeds are set by the admin (ICS_FEEDS)."""

from __future__ import annotations

import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import httpx

from app.core.logging_config import get_logger
from app.plugins.base import get_setting

logger = get_logger("service.ics")

MAX_BYTES = 2 * 1024 * 1024
CACHE_SECONDS = 30 * 60
_cache: Dict[str, Tuple[float, Optional[bytes]]] = {}


def clear_cache() -> None:
    _cache.clear()


def feed_id(name: str) -> str:
    return "ics:" + "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")


def parse_feeds(raw: Optional[str]) -> List[Tuple[str, str]]:
    """'Name | https://…' per line (or separated by ';'). Without a name, the host is used. Only http(s)."""
    feeds = []
    for entry in str(raw or "").replace(";", "\n").splitlines():
        entry = entry.strip()
        if not entry:
            continue
        name, _, url = entry.rpartition("|") if "|" in entry else ("", "", entry)
        url = url.strip()
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            logger.warning("Kalender-Abo ignoriert (nur http/https): %s", parts.scheme or "?")
            continue
        feeds.append((name.strip() or parts.hostname, url))
    return feeds


async def _fetch(url: str) -> Optional[bytes]:
    hit = _cache.get(url)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    data: Optional[bytes] = None
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True, max_redirects=3) as client:
            async with client.stream("GET", url, headers={"Accept": "text/calendar"}) as resp:
                if resp.status_code != 200:
                    raise httpx.HTTPStatusError(f"HTTP {resp.status_code}", request=resp.request, response=resp)
                chunks, size = [], 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("Kalender-Abo größer als 2 MB")
                    chunks.append(chunk)
                data = b"".join(chunks)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Kalender-Abo nicht lesbar (%s): %s", urlsplit(url).hostname, exc)
    _cache[url] = (time.monotonic(), data)  # failures are cached too, so a dead feed doesn't slow every request
    return data


def _fmt(value: Any) -> Tuple[str, bool]:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            from app.core.timeutil import local_tz

            value = value.astimezone(local_tz()).replace(tzinfo=None)
        return value.isoformat(), False
    if isinstance(value, date):
        return value.isoformat(), True
    return str(value), False


def _events(name: str, data: bytes, start: datetime, end: datetime) -> List[Dict[str, Any]]:
    import recurring_ical_events
    from icalendar import Calendar

    out = []
    cal = Calendar.from_ical(data)
    for ev in recurring_ical_events.of(cal, skip_bad_series=True).between(start, end):
        s, all_day = _fmt(ev.get("dtstart").dt)
        e_raw = ev.get("dtend")
        e = _fmt(e_raw.dt)[0] if e_raw is not None else s
        out.append({"title": str(ev.get("summary") or name), "start": s, "end": e, "all_day": all_day,
                    "location": str(ev.get("location")) if ev.get("location") else None,
                    "calendar": name, "calendar_id": feed_id(name), "source": "ics"})
    return out


async def events_between(start: datetime, end: datetime) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for name, url in parse_feeds(get_setting("ICS_FEEDS")):
        data = await _fetch(url)
        if not data:
            continue
        try:
            out.extend(_events(name, data, start, end))
        except Exception as exc:  # noqa: BLE001 - a broken feed must not break the calendar
            logger.warning("Kalender-Abo %s nicht auswertbar: %s", name, type(exc).__name__)
    return out


async def probe(url: str) -> Dict[str, Any]:
    """Checks a feed for the admin UI (not cached): reachable, a calendar, how many events in the next 90 days."""
    from datetime import timedelta

    if not parse_feeds(url):
        return {"ok": False, "error": "Nur http- oder https-Adressen", "events": 0, "sample": []}
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True, max_redirects=3) as client:
            resp = await client.get(url, headers={"Accept": "text/calendar"})
        if resp.status_code != 200:
            return {"ok": False, "error": f"Adresse antwortet mit HTTP {resp.status_code}", "events": 0, "sample": []}
        if len(resp.content) > MAX_BYTES:
            return {"ok": False, "error": "Kalender größer als 2 MB", "events": 0, "sample": []}
        now = datetime.now()
        events = _events("", resp.content, now, now + timedelta(days=90))
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"Nicht erreichbar ({type(exc).__name__})", "events": 0, "sample": []}
    except Exception:  # noqa: BLE001 - anything that doesn't parse is "not a calendar"
        return {"ok": False, "error": "Das ist keine Kalenderdatei (ICS)", "events": 0, "sample": []}
    events.sort(key=lambda e: e["start"])
    return {"ok": True, "error": None, "events": len(events), "sample": [e["title"] for e in events[:3]]}
