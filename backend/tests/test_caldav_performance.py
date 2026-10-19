"""CalDAV round trips, short read cache and parallel /api/today (#71), with a fake server that sleeps and counts."""

import asyncio
import time
from unittest.mock import patch

import pytest

from app.services import caldav_cache
from tests.caldav_fakes import BASE, FakeCalendar, FakeDAV, Server, app_start, setup_perf_user

@pytest.fixture
def perf(client):
    """A user with a CalDAV account on a slow fake server."""
    h = setup_perf_user(client)
    server = Server()
    with patch("caldav.DAVClient", side_effect=lambda **kw: FakeDAV(server, **kw)):
        yield server, h
    caldav_cache.reset()


def test_app_start_round_trips_and_time(client, perf):
    server, h = perf
    took = app_start(client, h)
    # Without sharing this was ~30 round trips (principal, calendars, components and colour per call, per list)
    assert len(server.calls) <= 20, server.calls
    assert took < 2.5, took
    calls = len(server.calls)
    again = app_start(client, h)
    assert len(server.calls) == calls and again < 0.5  # everything from the short cache


def _tasks(client, h, view="mine"):
    r = client.get(f"/api/tasks?view={view}", headers=h)
    assert r.status_code == 200
    return r.json()


def test_second_task_read_makes_no_caldav_call(client, perf):
    server, h = perf
    first = _tasks(client, h)
    assert first["items"] and first["status"] == "ok"
    calls = len(server.calls)
    assert calls > 0
    assert _tasks(client, h)["items"] == first["items"]
    assert len(server.calls) == calls  # served from the short cache


def test_calendar_list_and_client_are_shared_between_endpoints(client, perf):
    server, h = perf
    _tasks(client, h, "mine")
    _tasks(client, h, "family")  # other view: new read, same account
    assert client.get("/api/calendar/calendars", headers=h).status_code == 200
    assert client.get("/api/calendar/events?days=31", headers=h).status_code == 200
    assert server.clients == 1
    assert server.calls.count("principal") == 1 and server.calls.count("calendars") == 1
    # components once per calendar, colour once per calendar; one REPORT per event calendar, none for task lists
    assert server.calls.count("components") == 4 and server.calls.count("color") <= 4
    assert server.calls.count("events") == 2
    # "mine" reads my list and the family list (tasks assigned to me there), "family" the family list
    assert server.calls.count("todos") == 3


def test_task_lists_are_not_asked_for_events(client, perf):
    server, h = perf
    events = client.get("/api/calendar/events?days=31", headers=h).json()
    assert {e["calendar"] for e in events if e.get("source", "caldav") == "caldav"} == {"Privat", "Ferien"}


def test_changing_request_drops_the_read_cache(client, perf):
    server, h = perf
    _tasks(client, h)
    before = len(server.calls)
    client.post("/api/tasks/gibtsnicht/complete", headers=h)  # any change; the answer does not matter
    _tasks(client, h)
    assert len(server.calls) > before  # read again ...
    assert server.calls.count("calendars") == 1  # ... but the calendar list stays cached


def test_connector_write_drops_the_read_cache(perf):
    from app.connectors.nextcloud_tasks_connector import _invalidates

    caldav_cache.read_put(("tasks", "x"), {"items": [1]})
    _invalidates(lambda: None)()
    assert caldav_cache.read_get(("tasks", "x")) is None


def test_reads_are_keyed_by_user_and_account(perf):
    from app.connectors.nextcloud_tasks_connector import NextcloudTasksConnector

    a, b = NextcloudTasksConnector(user_id=1), NextcloudTasksConnector(user_id=2)
    a._account = {"url": BASE, "username": "anna", "password": "x"}
    b._account = {"url": BASE, "username": "ben", "password": "x"}
    assert a._account_key() != b._account_key()
    caldav_cache.read_put(("tasks", a._account_key(), 1, "mine", False), {"items": ["annas"]})
    assert caldav_cache.read_get(("tasks", b._account_key(), 2, "mine", False)) is None


def test_read_cache_expires(monkeypatch):
    caldav_cache.read_put("k", {"v": 1}, ttl=0.01)
    time.sleep(0.03)
    assert caldav_cache.read_get("k") is None


def test_failed_read_is_not_cached(client, perf, monkeypatch):
    server, h = perf
    monkeypatch.setattr(FakeCalendar, "todos", lambda self, include_completed=False: (_ for _ in ()).throw(RuntimeError("down")))
    assert _tasks(client, h)["items"] == []
    monkeypatch.undo()
    assert _tasks(client, h)["items"]  # recovers at once, no stale "empty" answer


# --- /api/today ---


def test_today_runs_sources_in_parallel(client, auth, monkeypatch):
    async def slow_events(*a, **k):
        await asyncio.sleep(0.4)
        return []

    async def slow_tasks(*a, **k):
        await asyncio.sleep(0.4)
        return {"status": "ok", "error": None, "items": []}

    monkeypatch.setattr("app.routers.calendar.collect_events", slow_events)
    monkeypatch.setattr("app.routers.tasks.read_tasks", slow_tasks)
    started = time.monotonic()
    r = client.get("/api/today", headers=auth)
    took = time.monotonic() - started
    assert r.status_code == 200 and r.json()["tasks"]["status"] == "ok"
    assert took < 0.7, f"sum, not max: {took:.2f}s"


def test_today_gives_up_on_a_slow_source(client, auth, monkeypatch):
    async def stuck(*a, **k):
        await asyncio.sleep(5)

    monkeypatch.setattr("app.routers.tasks.read_tasks", stuck)
    monkeypatch.setitem(__import__("app.routers.today", fromlist=["x"]).SOURCE_TIMEOUT, "tasks", 0.2)
    started = time.monotonic()
    r = client.get("/api/today", headers=auth).json()
    assert time.monotonic() - started < 2
    assert r["tasks"]["status"] == "unavailable" and r["tasks"]["items"] == []
    assert "date" in r and r["house"]["status"] == "not_configured"


def test_slow_sources_are_logged(caplog):
    import logging

    from app.core import timing

    async def run():
        async def work():
            await asyncio.sleep(0.05)
            return 1

        with caplog.at_level(logging.DEBUG, logger="hermes.timing"):
            assert await timing.timed("demo", work, timeout=1, default=0) == 1
            timing.SLOW_SECONDS, old = 0.01, timing.SLOW_SECONDS
            try:
                await timing.timed("demo2", work, timeout=1, default=0)
            finally:
                timing.SLOW_SECONDS = old

    asyncio.run(run())
    assert any(r.levelno == logging.DEBUG and "demo took" in r.message for r in caplog.records)
    assert any(r.levelno == logging.WARNING and "demo2 took" in r.message for r in caplog.records)
