"""Calendar plugins: third-party plugins with the ``calendar`` capability add read-only events and calendars."""

import asyncio
from datetime import datetime, timedelta

import pytest

from app.core.timeutil import local_tz
from app.plugins import Plugin
from app.plugins.registry import plugin_registry


TODAY = datetime.now(local_tz()).date()  # the hub counts days in local time, not the container clock


def _iso(days):
    return (TODAY + timedelta(days=days)).isoformat()


def _event(days=1, **extra):
    base = {"title": "Feiertag", "start": _iso(days), "end": _iso(days + 1), "all_day": True,
            "calendar": "Holidays", "calendar_id": "fakecal:public", "location": "DE", "description": "d", "color": "#112233"}
    return {**base, **extra}


class FakeCalendar(Plugin):
    """What a third-party plugin looks like to the hub; ``behaviour`` decides what the call does."""

    def __init__(self, plugin_id="fakecal", behaviour=None):
        super().__init__(id=plugin_id, name="Fake", capabilities=frozenset({"calendar"}))
        self.behaviour = behaviour or (lambda: [_event()])
        self.calls = []

    async def calendar_events(self, start, end, user, db):
        self.calls.append((start, end, getattr(user, "username", None)))
        result = self.behaviour()
        if asyncio.iscoroutine(result):
            result = await result
        return result

    def calendars(self, user, db):
        return [{"id": f"{self.id}:public", "name": "Holidays", "color": "#112233"},
                {"id": "ics:evil", "name": "Not mine", "color": None},
                {"id": f"{self.id}:school", "name": "School", "color": "red"}]


@pytest.fixture
def fake():
    plugin = FakeCalendar()
    assert plugin_registry.register(plugin)
    yield plugin
    plugin_registry.unregister(plugin.id)


def _events(client, auth, days=7):
    return client.get("/api/calendar/events", params={"days": days}, headers=auth).json()


def _raise():
    raise RuntimeError("boom")


def test_plugin_events_are_merged_read_only(client, auth, fake):
    found = [e for e in _events(client, auth) if e.get("source") == "fakecal"]
    assert len(found) == 1
    e = found[0]
    assert (e["title"], e["all_day"], e["calendar"], e["calendar_id"]) == ("Feiertag", True, "Holidays", "fakecal:public")
    assert (e["start"], e["end"], e["location"], e["description"], e["color"]) == (_iso(1), _iso(2), "DE", "d", "#112233")
    assert e["writable"] is False
    assert fake.calls and fake.calls[0][1] - fake.calls[0][0] == timedelta(days=7)


def test_plugin_cannot_set_source_or_writable_or_impersonate(client, auth):
    plugin = FakeCalendar(behaviour=lambda: [
        _event(1, source="hub", writable=True, id=5, uid="x"),
        _event(2, calendar_id="hub", title="Impostor"),
        _event(2, calendar_id="fakecal2:x", title="Prefix trick"),
        _event(2, calendar_id=None, title="No calendar"),
        _event(2, start=None, title="No start"),
        "junk",
        _event(3, color="url(javascript)"),
    ])
    plugin_registry.register(plugin)
    try:
        found = [e for e in _events(client, auth) if e["title"] in ("Feiertag", "Impostor", "Prefix trick", "No calendar", "No start")]
    finally:
        plugin_registry.unregister("fakecal")
    assert [e["title"] for e in found] == ["Feiertag", "Feiertag"]
    assert all(e["source"] == "fakecal" and e["writable"] is False and "id" not in e and "uid" not in e for e in found)
    assert "color" not in found[1]  # invalid colour dropped


def test_calendars_are_listed_with_source_and_valid_prefix(client, auth, fake):
    cals = [c for c in client.get("/api/calendar/calendars", headers=auth).json() if c["source"] == "fakecal"]
    assert cals == [
        {"id": "fakecal:public", "name": "Holidays", "source": "fakecal", "color": "#112233", "writable": False, "family": True},
        {"id": "fakecal:school", "name": "School", "source": "fakecal", "color": None, "writable": False, "family": True},
    ]


@pytest.mark.parametrize("behaviour", [_raise, lambda: {"not": "a list"}])
def test_failing_plugin_is_skipped_and_the_calendar_still_works(client, auth, behaviour):
    plugin_registry.register(FakeCalendar(behaviour=behaviour))
    try:
        events = _events(client, auth)
        assert client.get("/api/calendar/calendars", headers=auth).status_code == 200
    finally:
        plugin_registry.unregister("fakecal")
    assert isinstance(events, list) and not [e for e in events if e.get("source") == "fakecal"]


def test_a_failing_calendars_call_is_skipped(client, auth, fake, monkeypatch):
    monkeypatch.setattr(fake, "calendars", lambda user, db: _raise())
    response = client.get("/api/calendar/calendars", headers=auth)
    assert response.status_code == 200 and not [c for c in response.json() if c["source"] == "fakecal"]


def test_slow_plugin_times_out_and_is_skipped(client, auth, monkeypatch):
    from app.routers import calendar

    async def slow():
        await asyncio.sleep(5)
        return [_event()]

    monkeypatch.setattr(calendar, "PLUGIN_CALENDAR_TIMEOUT", 0.05)
    plugin_registry.register(FakeCalendar(behaviour=slow))
    try:
        events = _events(client, auth)
    finally:
        plugin_registry.unregister("fakecal")
    assert not [e for e in events if e.get("source") == "fakecal"]


def test_a_slow_plugin_does_not_hold_back_a_fast_one(client, auth, monkeypatch):
    from app.routers import calendar

    async def slow():
        await asyncio.sleep(5)
        return []

    monkeypatch.setattr(calendar, "PLUGIN_CALENDAR_TIMEOUT", 0.05)
    plugin_registry.register(FakeCalendar("slowcal", behaviour=slow))
    plugin_registry.register(FakeCalendar())
    try:
        events = _events(client, auth)
    finally:
        plugin_registry.unregister("slowcal")
        plugin_registry.unregister("fakecal")
    assert [e["source"] for e in events if e["title"] == "Feiertag"] == ["fakecal"]


def test_disabled_plugin_gives_nothing(client, auth, fake, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "plugins_disabled", "fakecal")
    assert not [e for e in _events(client, auth) if e.get("source") == "fakecal"]
    assert not [c for c in client.get("/api/calendar/calendars", headers=auth).json() if c["source"] == "fakecal"]
    assert fake.calls == []


def test_admin_source_choice_limits_plugins(client, auth, fake, monkeypatch):
    from app.services import config_store

    monkeypatch.setitem(config_store._extra, "CALENDAR_SOURCES", "hub_calendar")
    assert not [e for e in _events(client, auth) if e.get("source") == "fakecal"]


def test_hard_wired_ids_are_never_asked_as_plugins(client, auth):
    plugin = FakeCalendar("birthdays")
    plugin_registry.register(plugin)
    try:
        _events(client, auth)
    finally:
        plugin_registry.unregister("birthdays")
    assert plugin.calls == []


def test_todays_events_include_plugin_events(client, auth, fake):
    fake.behaviour = lambda: [_event(0, title="Heute frei")]
    today = client.get("/api/today", headers=auth).json()
    assert "Heute frei" in [e["title"] for e in today["events"]]
