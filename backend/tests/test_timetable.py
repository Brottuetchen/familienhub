"""Timetable of children: roles, copy day/week, A/B weeks, school holidays, Today card."""

import asyncio
from datetime import date, datetime, timedelta

import httpx
import respx

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.core.timeutil import local_tz
from app.models.timetable import TimetableEntry
from app.models.user import User

FEED = "https://feeds.example.test/ferien.ics"
BASE = "/api/timetable"


def _user(client, name, role, display=None):
    with SessionLocal() as db:
        u = db.query(User).filter(User.username == name).first()
        if not u:
            u = User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"),
                     role=role, display_name=display)
            db.add(u)
            db.commit()
            db.refresh(u)
        uid = u.id
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return uid, {"Authorization": f"Bearer {tok}"}


def _entry(child, weekday=0, start="08:00", end="09:00", title="Maths", kind="school", week="all"):
    return {"child_id": child, "weekday": weekday, "start": start, "end": end, "title": title, "kind": kind, "week": week}


def _add(client, headers, **kw):
    r = client.post(BASE, headers=headers, json=_entry(**kw))
    assert r.status_code == 201, r.text
    return r.json()


def _reset_settings(client, auth):
    client.put(f"{BASE}/settings", headers=auth, json={})


def test_parents_edit_children_only_view_own(client, auth):
    mia, mia_h = _user(client, "tt_mia", "child", "Mia")
    ben, ben_h = _user(client, "tt_ben", "child", "Ben")
    _, partner = _user(client, "tt_parent", "partner")
    _, guest = _user(client, "tt_guest", "guest")

    e = _add(client, partner, child=mia, title="Art")
    # children and guests may not write
    for h in (mia_h, guest):
        assert client.post(BASE, headers=h, json=_entry(mia)).status_code == 403
        assert client.patch(f"{BASE}/{e['id']}", headers=h, json={"title": "x"}).status_code == 403
        assert client.delete(f"{BASE}/{e['id']}", headers=h).status_code == 403
        assert client.post(f"{BASE}/copy-day", headers=h, json={"child_id": mia, "from_weekday": 0, "to_weekdays": [1]}).status_code == 403
        assert client.post(f"{BASE}/copy-week", headers=h, json={"child_id": mia, "from_week": "a", "to_week": "b"}).status_code == 403
        assert client.put(f"{BASE}/settings", headers=h, json={}).status_code == 403
    # a child sees their own timetable, not a sibling's; guests nothing
    own = client.get(BASE, headers=mia_h, params={"child_id": mia}).json()
    assert [x["title"] for x in own["entries"]] == ["Art"] and own["can_edit"] is False
    assert client.get(BASE, headers=mia_h, params={"child_id": ben}).status_code == 403
    assert client.get(BASE, headers=guest, params={"child_id": mia}).status_code == 403
    assert client.get(f"{BASE}/children", headers=mia_h).json() == [{"id": mia, "name": "Mia"}]
    assert client.get(f"{BASE}/children", headers=guest).json() == []
    # parents see every child and can edit
    ids = {c["id"] for c in client.get(f"{BASE}/children", headers=partner).json()}
    assert {mia, ben} <= ids
    got = client.get(BASE, headers=partner, params={"child_id": mia}).json()
    assert got["can_edit"] is True
    assert client.patch(f"{BASE}/{e['id']}", headers=partner, json={"title": "Drawing", "location": "Room 4"}).json()["title"] == "Drawing"
    assert client.delete(f"{BASE}/{e['id']}", headers=partner).status_code == 204
    assert client.get(BASE, headers=partner, params={"child_id": mia}).json()["entries"] == []


def test_validation(client, auth):
    mia, _ = _user(client, "tt_val", "child")
    _, partner = _user(client, "tt_parent", "partner")
    assert client.post(BASE, headers=partner, json=_entry(mia, start="10:00", end="09:00")).status_code == 422
    assert client.post(BASE, headers=partner, json=_entry(mia, start="8:00")).status_code == 422
    assert client.post(BASE, headers=partner, json=_entry(mia, weekday=7)).status_code == 422
    assert client.post(BASE, headers=partner, json=_entry(mia, kind="nap")).status_code == 422
    assert client.post(BASE, headers=partner, json=_entry(999999)).status_code == 404
    adult, _ = _user(client, "tt_adult", "partner")
    assert client.post(BASE, headers=partner, json=_entry(adult)).status_code == 404  # not a child
    e = _add(client, partner, child=mia)
    assert client.patch(f"{BASE}/{e['id']}", headers=partner, json={"end": "07:00"}).status_code == 422


def test_copy_day_and_week(client, auth):
    kid, _ = _user(client, "tt_copy", "child")
    _, partner = _user(client, "tt_parent", "partner")
    _add(client, partner, child=kid, weekday=0, title="Maths")
    _add(client, partner, child=kid, weekday=0, start="09:00", end="10:00", title="Music", kind="music")
    _add(client, partner, child=kid, weekday=1, title="Old")
    r = client.post(f"{BASE}/copy-day", headers=partner, json={"child_id": kid, "from_weekday": 0, "to_weekdays": [1, 2]})
    assert r.json() == {"copied": 4}
    rows = client.get(BASE, headers=partner, params={"child_id": kid}).json()["entries"]
    by_day = {d: sorted(e["title"] for e in rows if e["weekday"] == d) for d in (0, 1, 2)}
    assert by_day == {0: ["Maths", "Music"], 1: ["Maths", "Music"], 2: ["Maths", "Music"]}  # "Old" was replaced

    r = client.post(f"{BASE}/copy-week", headers=partner, json={"child_id": kid, "from_week": "all", "to_week": "b"})
    assert r.json() == {"copied": 6}
    rows = client.get(BASE, headers=partner, params={"child_id": kid}).json()["entries"]
    assert len([e for e in rows if e["week"] == "b"]) == 6 and len([e for e in rows if e["week"] == "all"]) == 6
    assert client.post(f"{BASE}/copy-week", headers=partner, json={"child_id": kid, "from_week": "b", "to_week": "b"}).status_code == 422


def test_ab_weeks(client, auth):

    kid, _ = _user(client, "tt_ab", "child")
    _, partner = _user(client, "tt_parent", "partner")
    _add(client, partner, child=kid, weekday=0, title="Both")
    _add(client, partner, child=kid, weekday=0, start="10:00", end="11:00", title="Only A", week="a")
    _add(client, partner, child=kid, weekday=0, start="11:00", end="12:00", title="Only B", week="b")
    monday = date(2026, 10, 19)
    try:
        assert client.put(f"{BASE}/settings", headers=partner, json={"ab_reference": "2026-10-21"}).status_code == 200
        with SessionLocal() as db:
            assert svc.week_variant(db, monday) == "a"
            assert svc.week_variant(db, monday + timedelta(days=7)) == "b"
            assert svc.week_variant(db, monday + timedelta(days=14)) == "a"
            assert svc.week_variant(db, monday - timedelta(days=7)) == "b"
            titles = lambda d: [e["title"] for e in svc.entries_on(db, kid, d, [])]  # noqa: E731
            assert titles(monday) == ["Both", "Only A"]
            assert titles(monday + timedelta(days=7)) == ["Both", "Only B"]
        # without a reference week only the "all" entries count
        client.put(f"{BASE}/settings", headers=partner, json={})
        with SessionLocal() as db:
            assert svc.week_variant(db, monday) is None
            assert [e["title"] for e in svc.entries_on(db, kid, monday, [])] == ["Both"]
    finally:
        _reset_settings(client, auth)


def _ics(start, end):
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//EN\r\nBEGIN:VEVENT\r\nUID:h\r\nSUMMARY:Autumn break\r\n"
            f"DTSTART;VALUE=DATE:{start:%Y%m%d}\r\nDTEND;VALUE=DATE:{end:%Y%m%d}\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")


def test_school_holidays_hide_lessons_but_not_leisure(client, auth, monkeypatch):
    from app.services import config_store, ics, timetable as svc

    kid, _ = _user(client, "tt_hol", "child", "Mia")
    _, partner = _user(client, "tt_parent", "partner")
    day = date(2026, 10, 20)  # Tuesday
    _add(client, partner, child=kid, weekday=1, title="Maths", end="13:15")
    _add(client, partner, child=kid, weekday=1, start="16:00", end="17:00", title="Swimming", kind="sport")
    ics.clear_cache()
    monkeypatch.setitem(config_store._extra, "ICS_FEEDS", f"School | {FEED}\nWaste | https://feeds.example.test/w.ics")
    try:
        assert client.put(f"{BASE}/settings", headers=partner, json={"holiday_feed": "ics:nope"}).status_code == 422
        r = client.put(f"{BASE}/settings", headers=partner, json={"holiday_feed": "ics:school"})
        assert r.json()["holiday_feed"] == "ics:school" and [f["id"] for f in r.json()["feeds"]] == ["ics:school", "ics:waste"]
        with respx.mock(using="httpx", assert_all_called=False) as http:
            http.route(host="testserver").pass_through()
            # holiday Mon 19 Oct to Fri 23 Oct (exclusive end Saturday)
            http.get(FEED).mock(return_value=httpx.Response(200, text=_ics(date(2026, 10, 19), date(2026, 10, 24))))
            http.get("https://feeds.example.test/w.ics").mock(return_value=httpx.Response(200, text=_ics(date(2026, 10, 21), date(2026, 10, 22))))
            with SessionLocal() as db:
                card = asyncio.run(svc.today_card(db, db.get(User, kid), day))
                periods = asyncio.run(svc.holidays(db, day, day))
            assert periods == [{"start": "2026-10-19", "end": "2026-10-23", "title": "Autumn break"}]
            assert card["children"][0]["holiday"] == "Autumn break"
            assert [e["title"] for e in card["children"][0]["entries"]] == ["Swimming"]
            with SessionLocal() as db:
                after = asyncio.run(svc.today_card(db, db.get(User, kid), date(2026, 10, 27)))
            assert [e["title"] for e in after["children"][0]["entries"]] == ["Maths", "Swimming"]
            assert after["children"][0]["holiday"] is None
    finally:
        ics.clear_cache()
        _reset_settings(client, auth)


def test_unreachable_holiday_feed_fails_softly(client, auth, monkeypatch):
    from app.services import config_store, ics, timetable as svc

    kid, _ = _user(client, "tt_soft", "child")
    _, partner = _user(client, "tt_parent", "partner")
    _add(client, partner, child=kid, weekday=1, title="Maths")
    ics.clear_cache()
    monkeypatch.setitem(config_store._extra, "ICS_FEEDS", f"School | {FEED}")
    client.put(f"{BASE}/settings", headers=partner, json={"holiday_feed": "ics:school"})
    try:
        with respx.mock(using="httpx", assert_all_called=False) as http:
            http.route(host="testserver").pass_through()
            http.get(FEED).mock(return_value=httpx.Response(500))
            with SessionLocal() as db:
                card = asyncio.run(svc.today_card(db, db.get(User, kid), date(2026, 10, 20)))
        assert card["status"] == "ok" and [e["title"] for e in card["children"][0]["entries"]] == ["Maths"]
    finally:
        ics.clear_cache()
        _reset_settings(client, auth)


def test_today_card_for_child_and_parent(client, auth):
    mia, mia_h = _user(client, "tt_today_mia", "child", "Mia")
    ben, _ = _user(client, "tt_today_ben", "child", "Ben")
    _, partner = _user(client, "tt_parent", "partner")
    _, guest = _user(client, "tt_guest", "guest")

    today = datetime.now(local_tz()).date()  # the hub counts days in its own time zone
    _add(client, partner, child=mia, weekday=today.weekday(), title="Maths", end="13:15")
    _add(client, partner, child=ben, weekday=today.weekday(), title="Football", kind="sport")
    kids = lambda h: {c["name"]: [e["title"] for e in c["entries"]] for c in client.get("/api/today", headers=h).json()["timetable"]["children"]}  # noqa: E731
    assert kids(mia_h) == {"Mia": ["Maths"]}  # own day only
    parent_view = kids(partner)
    assert parent_view["Mia"] == ["Maths"] and parent_view["Ben"] == ["Football"]
    assert kids(guest) == {}
    assert client.get(f"{BASE}/today", headers=mia_h).json()["children"][0]["name"] == "Mia"
    with SessionLocal() as db:
        db.query(TimetableEntry).filter(TimetableEntry.child_id.in_([mia, ben])).delete()
        db.commit()
