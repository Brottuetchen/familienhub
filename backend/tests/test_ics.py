"""Calendar subscriptions (ICS): school holidays, waste collection, clubs, read-only in the family calendar."""

from datetime import date, datetime, timedelta

import httpx
import pytest
import respx

FEED = "https://feeds.example.test/schule.ics"
WASTE = "https://feeds.example.test/abfall.ics"


def _ics(*events):
    body = "\r\n".join(events)
    return f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//EN\r\n{body}\r\nEND:VCALENDAR\r\n"


def _d(days):
    return (date.today() + timedelta(days=days)).strftime("%Y%m%d")


def _dt(days, hour):
    return (datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=days)).strftime("%Y%m%dT%H%M%S")


@pytest.fixture
def feeds(monkeypatch):
    from app.services import config_store, ics

    ics.clear_cache()
    monkeypatch.setitem(config_store._extra, "ICS_FEEDS", f"Schule | {FEED}\nAbfall | {WASTE}")
    yield
    ics.clear_cache()


def test_feed_events_appear_with_calendar_name(client, auth, feeds):
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()  # the test client itself
        http.get(FEED).mock(return_value=httpx.Response(200, text=_ics(
            f"BEGIN:VEVENT\r\nUID:a\r\nSUMMARY:Herbstferien\r\nDTSTART;VALUE=DATE:{_d(2)}\r\nDTEND;VALUE=DATE:{_d(9)}\r\nEND:VEVENT",
            f"BEGIN:VEVENT\r\nUID:b\r\nSUMMARY:Elternabend\r\nLOCATION:Aula\r\nDTSTART:{_dt(3, 19)}\r\nDTEND:{_dt(3, 21)}\r\nEND:VEVENT",
        )))
        http.get(WASTE).mock(return_value=httpx.Response(200, text=_ics(
            f"BEGIN:VEVENT\r\nUID:c\r\nSUMMARY:Gelbe Tonne\r\nDTSTART;VALUE=DATE:{_d(1)}\r\nEND:VEVENT")))
        events = client.get("/api/calendar/events", params={"days": 14}, headers=auth).json()
    ics_events = {e["title"]: e for e in events if e.get("source") == "ics"}
    assert set(ics_events) == {"Herbstferien", "Elternabend", "Gelbe Tonne"}
    assert ics_events["Herbstferien"]["all_day"] is True and ics_events["Herbstferien"]["calendar"] == "Schule"
    assert ics_events["Elternabend"]["location"] == "Aula" and ics_events["Elternabend"]["all_day"] is False
    assert ics_events["Gelbe Tonne"]["calendar"] == "Abfall"


def test_recurring_events_are_expanded(client, auth, feeds):
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()  # the test client itself
        http.get(FEED).mock(return_value=httpx.Response(200, text=_ics(
            f"BEGIN:VEVENT\r\nUID:r\r\nSUMMARY:Fußballtraining\r\nDTSTART:{_dt(0, 17)}\r\nDTEND:{_dt(0, 18)}\r\n"
            "RRULE:FREQ=DAILY;COUNT=30\r\nEND:VEVENT")))
        http.get(WASTE).mock(return_value=httpx.Response(200, text=_ics()))
        events = client.get("/api/calendar/events", params={"days": 7}, headers=auth).json()
    training = [e for e in events if e["title"] == "Fußballtraining"]
    assert 6 <= len(training) <= 8


def test_broken_feed_does_not_break_the_others(client, auth, feeds):
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()  # the test client itself
        http.get(FEED).mock(return_value=httpx.Response(500))
        http.get(WASTE).mock(return_value=httpx.Response(200, text=_ics(
            f"BEGIN:VEVENT\r\nUID:c\r\nSUMMARY:Biotonne\r\nDTSTART;VALUE=DATE:{_d(1)}\r\nEND:VEVENT")))
        r = client.get("/api/calendar/events", params={"days": 7}, headers=auth)
    assert r.status_code == 200
    assert "Biotonne" in {e["title"] for e in r.json()}


def test_feeds_are_cached(client, auth, feeds):
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()  # the test client itself
        route = http.get(FEED).mock(return_value=httpx.Response(200, text=_ics()))
        http.get(WASTE).mock(return_value=httpx.Response(200, text=_ics()))
        client.get("/api/calendar/events", headers=auth)
        client.get("/api/calendar/events", headers=auth)
    assert route.call_count == 1


def test_feed_list_parsing_and_rejects():
    from app.services.ics import parse_feeds

    feeds = parse_feeds("Schule | https://a.test/s.ics; https://b.test/x.ics\n  \nfile:///etc/passwd\nKaputt | ftp://c.test/x")
    assert feeds == [("Schule", "https://a.test/s.ics"), ("b.test", "https://b.test/x.ics")]


def test_too_large_feed_is_ignored(client, auth, feeds):
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()  # the test client itself
        http.get(FEED).mock(return_value=httpx.Response(200, content=b"x" * (3 * 1024 * 1024)))
        http.get(WASTE).mock(return_value=httpx.Response(200, text=_ics()))
        assert client.get("/api/calendar/events", headers=auth).status_code == 200


def test_plugin_inactive_without_feeds(client, auth):
    body = client.get("/api/modules", headers=auth).json()
    ics = next(p for p in body["plugins"] if p["id"] == "ics")
    assert ics["active"] is False
