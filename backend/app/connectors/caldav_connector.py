"""Kalender-Connector via CalDAV (Nextcloud, iCloud, Radicale, ...).

Unterstützt gemeinsame Familienkalender inkl. Farbcodierung. Zusätzliche
Kalender (Feiertage, Ferien, Müllkalender) werden automatisch mitgelesen,
sofern sie im CalDAV-Server abonniert sind.

Die ``caldav``-Bibliothek arbeitet synchron; die Aufrufe werden daher in einem
Thread ausgeführt, um den async Event-Loop nicht zu blockieren.
"""

from __future__ import annotations

import asyncio
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from app.config import settings
from app.connectors.base import BaseConnector


class CalDAVConnector(BaseConnector):
    name = "caldav"
    display_name = "Kalender (CalDAV/Nextcloud)"
    category = "calendar"
    icon = "📅"

    def __init__(
        self,
        url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        """Ohne Argumente gelten die globalen Einstellungen, sonst das Konto eines Nutzers."""
        super().__init__()
        self._url = url
        self._username = username
        self._password = password

    @property
    def url(self) -> Optional[str]:
        return self._url or settings.caldav_url

    @property
    def username(self) -> Optional[str]:
        return self._username or settings.caldav_username

    @property
    def password(self) -> Optional[str]:
        return self._password or settings.caldav_password

    @property
    def is_configured(self) -> bool:
        return bool(self.url and self.username and self.password)

    @property
    def base_url(self) -> Optional[str]:
        return self.url

    async def _probe(self) -> bool:
        events = await self.get_events(days_ahead=1)
        # Erfolgreiche (auch leere) Antwort bedeutet: erreichbar.
        return events is not None

    async def get_events(
        self, days_ahead: int = 7, start: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Termine im angegebenen Zeitfenster (Standard: nächste 7 Tage)."""
        if not self.is_configured:
            return []
        start = start or datetime.now()
        end = start + timedelta(days=days_ahead)
        try:
            return await asyncio.to_thread(self._fetch_events_sync, start, end)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("caldav get_events failed: %s", exc)
            return []

    async def list_calendars(self) -> List[Dict[str, Any]]:
        """Calendars of this account that hold events: id, name, colour, url."""
        if not self.is_configured:
            return []
        try:
            return await asyncio.to_thread(self._list_calendars_sync)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("caldav list_calendars failed: %s", exc)
            return []

    def _list_calendars_sync(self) -> List[Dict[str, Any]]:
        import caldav

        client = caldav.DAVClient(url=self.url, username=self.username, password=self.password,
                                  ssl_verify_cert=settings.verify_tls)
        out = []
        for cal in client.principal().calendars():
            components = _safe(lambda: [str(c).upper() for c in cal.get_supported_components()]) or ["VEVENT"]
            if "VEVENT" not in components:
                continue  # task-only lists (VTODO)
            url = str(cal.url)
            out.append({"id": calendar_id(url), "name": _safe(lambda: str(cal.name)) or "Kalender",
                        "color": calendar_color(cal), "url": url})
        return out

    async def update_event(self, calendar_url: str, uid: str, changes: Dict[str, Any]) -> bool:
        """Changes title/location/notes (and times for single events). False if the event isn't there."""
        return await asyncio.to_thread(self._update_event_sync, calendar_url, uid, changes)

    async def delete_event(self, calendar_url: str, uid: str) -> bool:
        return await asyncio.to_thread(self._delete_event_sync, calendar_url, uid)

    def _event_by_uid(self, calendar_url: str, uid: str):
        import caldav
        from caldav.lib.error import NotFoundError

        client = caldav.DAVClient(url=self.url, username=self.username, password=self.password,
                                  ssl_verify_cert=settings.verify_tls)
        wanted = _normalize_url(calendar_url)
        cal = next((c for c in client.principal().calendars() if _normalize_url(str(c.url)) == wanted), None)
        if cal is None:
            return None
        try:
            return cal.event_by_uid(uid)
        except NotFoundError:
            return None

    def _update_event_sync(self, calendar_url: str, uid: str, changes: Dict[str, Any]) -> bool:
        ev = self._event_by_uid(calendar_url, uid)
        if ev is None:
            return False
        comp = ev.icalendar_component
        series = bool(comp.get("rrule"))
        for key, prop in (("title", "summary"), ("location", "location"), ("notes", "description")):
            if key in changes:
                comp.pop(prop, None)
                if changes[key]:
                    comp.add(prop, changes[key])
        if not series and "start" in changes and "end" in changes:
            for prop in ("dtstart", "dtend"):
                comp.pop(prop, None)
            if changes.get("all_day"):
                comp.add("dtstart", datetime.fromisoformat(changes["start"]).date())
                comp.add("dtend", datetime.fromisoformat(changes["end"]).date())
            else:
                comp.add("dtstart", _local_time(changes["start"]))
                comp.add("dtend", _local_time(changes["end"]))
        ev.save()
        return True

    def _delete_event_sync(self, calendar_url: str, uid: str) -> bool:
        ev = self._event_by_uid(calendar_url, uid)
        if ev is None:
            return False
        ev.delete()
        return True

    async def get_today(self) -> List[Dict[str, Any]]:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        events = await self.get_events(days_ahead=1, start=today)
        end = today + timedelta(days=1)
        return [e for e in events if _event_on_day(e, today, end)]

    async def create_event(
        self,
        title: str,
        start: str,
        end: str,
        all_day: bool,
        calendar_url: Optional[str] = None,
        **extras: Any,
    ) -> Dict[str, Any]:
        """Erstellt einen neuen Kalendereintrag. ``extras``: location, notes, rrule (DAILY/WEEKLY/MONTHLY/YEARLY).

        Args:
            title: Titel des Events
            start: ISO 8601 Start-Zeit
            end: ISO 8601 End-Zeit
            all_day: Ganztägiger Termin
            calendar_url: Optional, URL des Zielkalenders

        Returns:
            Dict mit den Eventdaten
        """
        if not self.is_configured:
            raise ValueError("CalDAV not configured")

        return await asyncio.to_thread(
            self._create_event_sync,
            title,
            start,
            end,
            all_day,
            calendar_url,
            **extras,
        )

    # --- Synchrone CalDAV-Logik (läuft im Thread) ---

    def _fetch_events_sync(self, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        try:
            import caldav  # lazy import – optionaler Dependency
        except ImportError:
            self.logger.warning("python 'caldav' package not installed – calendar disabled")
            return []

        client = caldav.DAVClient(
            url=self.url,
            username=self.username,
            password=self.password,
            ssl_verify_cert=settings.verify_tls,
        )
        principal = client.principal()
        results: List[Dict[str, Any]] = []

        for calendar in principal.calendars():
            cal_id = calendar_id(str(calendar.url))  # before search(), which rewrites calendar.url
            cal_name = _safe(lambda: str(calendar.name)) or "Kalender"
            cal_color = calendar_color(calendar)
            try:
                found = calendar.search(start=start, end=end, event=True, expand=True)
            except Exception:  # noqa: BLE001
                # Nicht alle Server unterstützen expand/search identisch.
                found = calendar.date_search(start=start, end=end)

            for ev in found:
                comp = _safe(lambda: ev.icalendar_component)
                if comp is None:
                    continue
                results.append({**_component_to_event(comp, cal_name, cal_color), "calendar_id": cal_id})

        results.sort(key=lambda e: e.get("start") or "")
        return results

    def _create_event_sync(
        self,
        title: str,
        start: str,
        end: str,
        all_day: bool,
        calendar_url: Optional[str] = None,
        location: Optional[str] = None,
        notes: Optional[str] = None,
        rrule: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Erstellt synchron ein Event via CalDAV."""
        try:
            import caldav
            from icalendar import Calendar, Event
            from uuid import uuid4
        except ImportError:
            self.logger.warning("python 'caldav' or 'icalendar' package not installed")
            raise ValueError("caldav library not available")

        client = caldav.DAVClient(
            url=self.url,
            username=self.username,
            password=self.password,
            ssl_verify_cert=settings.verify_tls,
        )
        principal = client.principal()
        calendars = principal.calendars()

        if not calendars:
            raise ValueError("No calendar found")

        # Exactly the chosen calendar; without a choice the first one (old behaviour)
        target_calendar = calendars[0]
        if calendar_url:
            wanted = _normalize_url(calendar_url)
            target_calendar = next((c for c in calendars if _normalize_url(str(c.url)) == wanted), None)
            if target_calendar is None:
                raise ValueError("Kalender nicht gefunden")

        # iCalendar Event erstellen
        cal = Calendar()
        event = Event()
        event.add('uid', str(uuid4()))
        event.add('summary', title)
        event.add('dtstamp', datetime.now())

        if all_day:
            # Ganztägig: DATE ohne Zeit
            start_date = datetime.fromisoformat(start.replace("Z", "+00:00")).date()
            end_date = datetime.fromisoformat(end.replace("Z", "+00:00")).date()
            event.add('dtstart', start_date)
            event.add('dtend', end_date)
        else:
            # Mit Zeit: DATETIME
            event.add('dtstart', _local_time(start))
            event.add('dtend', _local_time(end))

        if location:
            event.add('location', location)
        if notes:
            event.add('description', notes)
        if rrule:
            event.add('rrule', {'freq': rrule})
        cal.add_component(event)

        # Event speichern
        target_calendar.save_event(cal.to_ical().decode('utf-8'))

        return {
            "uid": str(event.get('uid')),
            "title": title,
            "start": start,
            "end": end,
            "all_day": all_day,
        }


# --- Hilfsfunktionen ---

def _local_time(value: str) -> datetime:
    """ISO time in the hub's time zone (TZID=Europe/Berlin instead of a fixed +02:00 offset).

    A fixed offset makes servers guess a zone (Nextcloud picks e.g. Africa/Blantyre), and
    repeating events then shift by an hour after the daylight saving change.
    """
    from app.core.timeutil import local_tz

    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt.replace(tzinfo=local_tz()) if dt.tzinfo is None else dt.astimezone(local_tz())


def calendar_id(url: str) -> str:
    """Stable, non-revealing id of a CalDAV calendar (the URL contains user names)."""
    from hashlib import sha256

    return "caldav:" + sha256(_normalize_url(url).encode()).hexdigest()[:12]


def _normalize_url(url: str) -> str:
    """Same calendar, same string: drop default ports (the caldav library adds ":443" after a search)."""
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url.rstrip("/"))
    netloc = parts.netloc
    if (parts.scheme == "https" and netloc.endswith(":443")) or (parts.scheme == "http" and netloc.endswith(":80")):
        netloc = netloc.rsplit(":", 1)[0]
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))

CALENDAR_COLOR_TAG = "{http://apple.com/ns/ical/}calendar-color"

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def normalize_color(raw: Any) -> Optional[str]:
    """``#RGB``, ``#RRGGBB`` or ``#RRGGBBAA`` (Nextcloud) -> ``#RRGGBB`` upper case; anything else -> None.

    Never returns the string "None": a missing property must stay missing so the app uses its palette.
    """
    if not isinstance(raw, str):
        return None
    m = _HEX_RE.match(raw.strip())
    if not m:
        return None
    digits = m.group(1)
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    return "#" + digits[:6].upper()


def calendar_color(cal: Any) -> Optional[str]:
    """Colour of a CalDAV calendar (Apple ``calendar-color`` property) as ``#RRGGBB``, or None.

    ``caldav.elements.ical`` is not imported by ``import caldav``; it has to be imported explicitly,
    otherwise the lookup fails with AttributeError and every calendar looks colourless.
    """
    try:
        from caldav.elements.ical import CalendarColor

        props = cal.get_properties([CalendarColor()])
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(props, dict):
        return None
    value = props.get(CALENDAR_COLOR_TAG)
    if value is None:  # some servers key the answer differently; match by tag suffix
        value = next((v for k, v in props.items() if str(k).endswith("calendar-color")), None)
    return normalize_color(value)


def _component_to_event(comp: Any, cal_name: str, cal_color: Optional[str]) -> Dict[str, Any]:
    summary = str(comp.get("summary", "Termin"))
    dtstart = comp.get("dtstart")
    dtend = comp.get("dtend")
    start_val = getattr(dtstart, "dt", None)
    end_val = getattr(dtend, "dt", None)
    all_day = isinstance(start_val, date) and not isinstance(start_val, datetime)
    return {
        "title": summary,
        "start": _iso(start_val),
        "end": _iso(end_val),
        "all_day": all_day,
        "location": str(comp.get("location", "")) or None,
        "notes": str(comp.get("description", "")) or None,
        "uid": str(comp.get("uid", "")) or None,
        # Part of a series: editing changes the whole series
        "recurring": bool(comp.get("rrule") or comp.get("recurrence-id")),
        "calendar": cal_name,
        "color": cal_color or None,  # no invented default: the app colours by calendar id
    }


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _event_on_day(event: Dict[str, Any], day_start: datetime, day_end: datetime) -> bool:
    start = event.get("start")
    if not start:
        return False
    try:
        s = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
        s = s.replace(tzinfo=None)
    except ValueError:
        try:
            s = datetime.combine(date.fromisoformat(str(start)), datetime.min.time())
        except ValueError:
            return False
    return day_start <= s < day_end


def _safe(fn):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return None
