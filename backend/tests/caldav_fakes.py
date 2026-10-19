"""Fake CalDAV server for the performance tests: sleeps and counts every round trip."""

import time
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

from icalendar import Calendar

BASE = "https://cloud.perf.example/remote.php/dav"
LATENCY = 0.05


class Server:
    """Counts every round trip and sleeps for each one."""

    def __init__(self, latency=LATENCY):
        self.latency = latency
        self.calls = []
        self.clients = 0

    def hit(self, what):
        self.calls.append(what)
        time.sleep(self.latency)


class FakeTodo:
    def __init__(self, uid, summary):
        cal = Calendar.from_ical(f"BEGIN:VCALENDAR\nBEGIN:VTODO\nUID:{uid}\nSUMMARY:{summary}\nEND:VTODO\nEND:VCALENDAR\n")
        self.icalendar_component = next(c for c in cal.walk() if c.name == "VTODO")


class FakeEvent:
    def __init__(self, uid, summary):
        start = datetime.now().replace(hour=23, minute=0, second=0, microsecond=0)
        cal = Calendar.from_ical(
            f"BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:{uid}\nSUMMARY:{summary}\n"
            f"DTSTART:{start:%Y%m%dT%H%M%S}\nDTEND:{start + timedelta(hours=1):%Y%m%dT%H%M%S}\nEND:VEVENT\nEND:VCALENDAR\n")
        self.icalendar_component = next(c for c in cal.walk() if c.name == "VEVENT")


class FakeCalendar:
    def __init__(self, server, name, components):
        self.server, self.name, self.components = server, name, components
        self.url = f"{BASE}/calendars/perf/{name}"

    def get_supported_components(self):
        self.server.hit("components")
        return self.components

    def get_properties(self, props):
        self.server.hit("color")
        return {"{http://apple.com/ns/ical/}calendar-color": "#112233"}

    def todos(self, include_completed=False):
        self.server.hit("todos")
        return [FakeTodo(f"{self.name}-1", f"Aufgabe {self.name}")]

    def search(self, **kwargs):
        self.server.hit("events")
        return [FakeEvent(f"{self.name}-e", f"Termin {self.name}")]


class FakeDAV:
    def __init__(self, server, **kwargs):
        self.server = server
        server.clients += 1

    def principal(self):
        self.server.hit("principal")
        return NS(calendars=self._calendars)

    def _calendars(self):
        self.server.hit("calendars")
        return [FakeCalendar(self.server, "Anna", ["VTODO"]), FakeCalendar(self.server, "Familie", ["VTODO"]),
                FakeCalendar(self.server, "Privat", ["VEVENT"]), FakeCalendar(self.server, "Ferien", ["VEVENT"])]




def setup_perf_user(client):
    """A user with a CalDAV account (2 task lists, 2 event calendars); returns the auth header."""
    from app.core.crypto import encrypt
    from app.core.database import SessionLocal
    from app.core.security import get_password_hash
    from app.models.caldav import CalDAVAccount, TaskList
    from app.models.user import User

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "perf_anna").first()
        if not user:
            user = User(username="perf_anna", email="perf@test.de", hashed_password=get_password_hash("pw-12345"),
                        role="partner")
            db.add(user)
            db.commit()
            db.refresh(user)
        db.query(CalDAVAccount).filter(CalDAVAccount.user_id == user.id).delete()
        db.query(TaskList).filter(TaskList.user_id == user.id).delete()
        db.add(CalDAVAccount(user_id=user.id, url=BASE, username="anna", password_enc=encrypt("secret")))
        db.add(TaskList(user_id=user.id, caldav_url=f"{BASE}/calendars/perf/Anna", display_name="Anna",
                        kind="personal", owner_user_id=user.id))
        db.add(TaskList(user_id=user.id, caldav_url=f"{BASE}/calendars/perf/Familie", display_name="Familie", kind="family"))
        db.commit()
    tok = client.post("/api/auth/login", json={"username": "perf_anna", "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def app_start(client, h):
    """What the app asks for when it opens: today, three task views, calendar list, a month of events."""
    started = time.monotonic()
    for path in ("/api/today", "/api/tasks?view=mine", "/api/tasks?view=for_me", "/api/tasks?view=family",
                 "/api/calendar/calendars", "/api/calendar/events?days=31"):
        assert client.get(path, headers=h).status_code == 200, path
    return time.monotonic() - started
