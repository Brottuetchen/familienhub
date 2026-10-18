"""Kalender-Connector via CalDAV (Nextcloud, iCloud, Radicale, ...).

Unterstützt gemeinsame Familienkalender inkl. Farbcodierung. Zusätzliche
Kalender (Feiertage, Ferien, Müllkalender) werden automatisch mitgelesen,
sofern sie im CalDAV-Server abonniert sind.

Die ``caldav``-Bibliothek arbeitet synchron; die Aufrufe werden daher in einem
Thread ausgeführt, um den async Event-Loop nicht zu blockieren.
"""

from __future__ import annotations

import asyncio
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
                        "color": _safe(lambda: str(cal.get_property(_color_prop()))), "url": url})
        return out

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
    ) -> Dict[str, Any]:
        """Erstellt einen neuen Kalendereintrag.

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
            cal_name = _safe(lambda: str(calendar.name)) or "Kalender"
            cal_color = _safe(lambda: str(calendar.get_property(_color_prop())))
            try:
                found = calendar.search(start=start, end=end, event=True, expand=True)
            except Exception:  # noqa: BLE001
                # Nicht alle Server unterstützen expand/search identisch.
                found = calendar.date_search(start=start, end=end)

            cal_id = calendar_id(str(calendar.url))
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

        # Ersten Kalender nehmen (oder den angegebenen)
        target_calendar = calendars[0]
        if calendar_url:
            for cal in calendars:
                if calendar_url in str(cal.url):
                    target_calendar = cal
                    break

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
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
            event.add('dtstart', start_dt)
            event.add('dtend', end_dt)

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

def calendar_id(url: str) -> str:
    """Stable, non-revealing id of a CalDAV calendar (the URL contains user names)."""
    from hashlib import sha256

    return "caldav:" + sha256(url.rstrip("/").encode()).hexdigest()[:12]

def _color_prop():
    try:
        import caldav

        return caldav.elements.ical.CalendarColor()
    except Exception:  # noqa: BLE001
        return None


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
        "calendar": cal_name,
        "color": cal_color or "#4f46e5",
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
