"""Event reminders: alarms in CalDAV and hub events, hub notifications for people without the calendar on their phone."""

import asyncio
from datetime import datetime, timedelta

from icalendar import Event

from app.services import event_alarms
from app.services.event_alarms import alarm_minutes, due, message, set_alarm


def test_alarm_is_written_and_read_back():
    ev = Event()
    ev.add("summary", "Zahnarzt")
    ev.add("dtstart", datetime(2026, 10, 20, 10, 0))
    set_alarm(ev, 15, "Zahnarzt")
    ical = ev.to_ical().decode()
    assert "BEGIN:VALARM" in ical and "TRIGGER:-PT15M" in ical and "ACTION:DISPLAY" in ical
    assert alarm_minutes(Event.from_ical(ical)) == 15
    set_alarm(ev, 0, "Zahnarzt")  # replaces, at the start
    assert alarm_minutes(ev) == 0 and ev.to_ical().decode().count("BEGIN:VALARM") == 1
    set_alarm(ev, None, "Zahnarzt")
    assert alarm_minutes(ev) is None and "VALARM" not in ev.to_ical().decode()


def test_absolute_trigger_counts_against_the_start():
    ical = ("BEGIN:VEVENT\r\nSUMMARY:X\r\nDTSTART:20261020T100000\r\nBEGIN:VALARM\r\nACTION:DISPLAY\r\n"
            "TRIGGER;VALUE=DATE-TIME:20261020T093000\r\nEND:VALARM\r\nEND:VEVENT\r\n")
    assert alarm_minutes(Event.from_ical(ical)) == 30


def test_due_window_and_message():
    now = datetime(2026, 10, 20, 9, 45)
    events = [
        {"uid": "a", "title": "Zahnarzt", "start": "2026-10-20T10:00:00", "alarm_minutes": 15, "calendar": "Persoenlich"},
        {"uid": "b", "title": "Später", "start": "2026-10-20T11:00:00", "alarm_minutes": 15},
        {"uid": "c", "title": "Ohne", "start": "2026-10-20T09:50:00", "alarm_minutes": None},
        {"uid": "d", "title": "Verpasst", "start": "2026-10-20T09:00:00", "alarm_minutes": 15},  # 30 min ago
        {"uid": "e", "title": "Ferien", "start": "2026-10-21", "all_day": True, "alarm_minutes": 1440},
    ]
    keys = {e["uid"] for _k, _f, e in due(events, now)}
    assert keys == {"a"}
    assert {e["uid"] for _k, _f, e in due(events, datetime(2026, 10, 20, 0, 3))} == {"e"}  # day before, midnight
    assert message(events[0], now) == ("📅 Zahnarzt", "Um 10:00 Uhr · Persoenlich")
    assert message(events[4], datetime(2026, 10, 20, 0, 3)) == ("📅 Ferien", "Morgen")


def test_hub_event_keeps_its_alarm(client, auth):
    start = (datetime.now() + timedelta(days=3)).replace(microsecond=0, second=0)
    r = client.post("/api/calendar/events", headers=auth, json={
        "title": "Elternabend", "start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat(),
        "all_day": False, "calendar_id": "hub", "alarm_minutes": 30})
    assert r.status_code == 201 and r.json()["alarm_minutes"] == 30
    eid = r.json()["id"]
    body = {"title": "Elternabend", "start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat(), "all_day": False}
    assert client.put(f"/api/calendar/events/{eid}", headers=auth, json=body).json()["alarm_minutes"] == 30  # not sent: kept
    assert client.put(f"/api/calendar/events/{eid}", headers=auth, json={**body, "alarm_minutes": None}).json()["alarm_minutes"] is None


def test_caldav_event_gets_a_valarm(monkeypatch):
    import caldav

    from app.connectors.caldav_connector import CalDAVConnector, _component_to_event

    saved = []

    class FakeCalendar:
        url = "https://cloud.example.org/remote.php/dav/calendars/anna/privat/"

        def save_event(self, ical):
            saved.append(ical)

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        def principal(self):
            return type("P", (), {"calendars": lambda self: [FakeCalendar()]})()

    monkeypatch.setattr(caldav, "DAVClient", FakeClient)
    from app.services import caldav_cache

    caldav_cache.invalidate_account() if hasattr(caldav_cache, "invalidate_account") else None
    conn = CalDAVConnector(url="https://cloud.example.org/remote.php/dav", username="anna", password="pw")
    conn._create_event_sync("Elternabend", "2026-10-20T19:00:00+02:00", "2026-10-20T20:00:00+02:00", False,
                            None, alarm_minutes=0)
    assert "BEGIN:VALARM" in saved[0] and ("TRIGGER:P0D" in saved[0] or "TRIGGER:PT0S" in saved[0])  # both mean 0
    from icalendar import Calendar

    comp = next(c for c in Calendar.from_ical(saved[0]).walk("VEVENT"))
    assert _component_to_event(comp, "Privat", None)["alarm_minutes"] == 0


def test_hub_notifies_only_people_without_the_calendar_on_their_phone(client, auth, monkeypatch):
    from app.core.database import SessionLocal
    from app.models.notification_log import NotificationLog
    from app.models.user import User
    from app.routers import calendar as calendar_router

    from app.core.timeutil import local_tz

    # "now" in the hub's time zone (another test may set it; the build server runs in UTC)
    soon = (datetime.now(local_tz()).replace(tzinfo=None) + timedelta(minutes=10)).replace(second=0, microsecond=0)
    events = [{"uid": "zahn-1", "title": "Zahnarzt", "start": soon.isoformat(), "alarm_minutes": 15, "calendar": "Familie"},
              {"uid": "feiertag", "title": "Feiertag", "start": soon.isoformat(), "alarm_minutes": None}]

    async def fake_collect(db, user, days, start=None):
        return events

    monkeypatch.setattr(calendar_router, "collect_events", fake_collect)
    with SessionLocal() as db:
        ids = [u.id for u in db.query(User).filter(User.is_active == True).all()]  # noqa: E712
        admin = db.query(User).filter(User.username == "admin").one()
        admin_id = admin.id
    r = client.put("/api/calendar/me/reminders", headers=auth, json={"calendar_on_phone": True})
    assert r.status_code == 200 and r.json() == {"calendar_on_phone": True}, (r.status_code, r.text)

    def logged(uid):
        with SessionLocal() as db:
            return db.query(NotificationLog).filter(NotificationLog.user_id == uid,
                                                    NotificationLog.title == "📅 Zahnarzt").count()

    before = {i: logged(i) for i in ids}
    sent = asyncio.run(event_alarms.send_due())
    assert sent == len(ids) - 1  # everyone but the admin (calendar on the phone)
    assert logged(admin_id) == before[admin_id]
    assert all(logged(i) == before[i] + 1 for i in ids if i != admin_id)
    assert asyncio.run(event_alarms.send_due()) == 0  # once per event and alarm
    assert client.get("/api/calendar/me/reminders", headers=auth).json() == {"calendar_on_phone": True}
    client.put("/api/calendar/me/reminders", headers=auth, json={"calendar_on_phone": False})
