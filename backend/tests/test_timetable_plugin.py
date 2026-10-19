"""Timetable from plugins: child mapping, merge with manual entries, cancelled lessons, soft failures."""

import asyncio
from datetime import date, timedelta

import pytest

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.timetable import TimetableEntry, TimetableSource
from app.models.user import User
from app.plugins.base import Plugin
from app.plugins.registry import plugin_registry
from app.services import timetable_plugin

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


def _monday():
    today = date.today()
    return today - timedelta(days=today.weekday()) + timedelta(days=7)  # next week: nothing is "past"


class SchoolPlugin(Plugin):
    """The simulated school system: lessons Monday to Friday, except what ``skip`` removes."""

    def __init__(self):
        super().__init__(id="fakeschool", name="Fake School", capabilities=frozenset({"timetable"}))
        self.calls = []
        self.fail = False
        self.hang = False
        self.skip = set()  # ISO days without data (holidays)
        self.people = [{"id": "p1", "name": "Mia Muster"}, {"id": "p2", "name": "Ben Beispiel"}]

    async def timetable(self, child, start, end, db):
        self.calls.append((child, start, end))
        if self.hang:
            await asyncio.sleep(30)
        if self.fail:
            raise RuntimeError("token abc123 expired")
        out = []
        day = start
        while day <= end:
            if day.weekday() < 5 and day.isoformat() not in self.skip:
                out.append({"date": day.isoformat(), "start": "08:00", "end": "08:45", "title": f"Maths {child.person_id}",
                            "kind": "school", "location": "R1", "status": "cancelled" if day.weekday() == 1 else "normal",
                            "note": "Teacher ill" if day.weekday() == 1 else None, "teacher": "Mr X", "period": 1})
                out.append({"date": day.isoformat(), "start": "08:50", "end": "09:35", "title": "English",
                            "kind": "school", "status": "substitution" if day.weekday() == 2 else "normal", "period": 2})
                out.append({"date": "garbage", "start": "08:00", "end": "09:00", "title": "x"})
                out.append({"date": day.isoformat(), "start": "9:00", "end": "10:00", "title": "bad time"})
                out.append("not a dict")
            day += timedelta(days=1)
        return out

    async def timetable_people(self):
        return self.people


@pytest.fixture
def school():
    timetable_plugin.clear_cache()
    plugin = SchoolPlugin()
    plugin_registry.register(plugin)
    yield plugin
    plugin_registry.unregister("fakeschool")
    timetable_plugin.clear_cache()
    with SessionLocal() as db:
        db.query(TimetableSource).delete()
        db.query(TimetableEntry).filter(TimetableEntry.title.like("TP %")).delete(synchronize_session=False)
        db.commit()


def _manual(client, h, child, title, weekday, kind="school", start="08:00", end="09:00"):
    r = client.post(BASE, headers=h, json={"child_id": child, "weekday": weekday, "start": start, "end": end,
                                           "title": title, "kind": kind})
    assert r.status_code == 201, r.text


def _map(client, h, child, person="p1", plugin="fakeschool"):
    r = client.put(f"{BASE}/sources", headers=h, json={"sources": [{"child_id": child, "plugin_id": plugin, "person_id": person}]})
    return r


def test_mapping_roles_validation_and_people(client, school):
    mia, mia_h = _user(client, "tp_mia", "child", "Mia")
    _, parent = _user(client, "tp_parent", "partner")
    _, guest = _user(client, "tp_guest", "guest")
    assert client.get(f"{BASE}/sources", headers=mia_h).status_code == 403
    assert client.put(f"{BASE}/sources", headers=mia_h, json={"sources": []}).status_code == 403
    assert client.get(f"{BASE}/sources", headers=guest).status_code == 403

    view = client.get(f"{BASE}/sources", headers=parent).json()
    assert view["plugins"] == [{"id": "fakeschool", "name": "Fake School", "people": school.people, "people_known": True}]
    assert next(c for c in view["children"] if c["child_id"] == mia)["plugin_id"] is None

    assert _map(client, parent, mia, person="nobody").status_code == 422  # not in timetable_people
    assert _map(client, parent, mia, plugin="nope").status_code == 422
    assert _map(client, parent, 999999).status_code == 404
    ok = _map(client, parent, mia, person="p1").json()
    row = next(c for c in ok["children"] if c["child_id"] == mia)
    assert (row["plugin_id"], row["person_id"], row["person_name"]) == ("fakeschool", "p1", "Mia Muster")
    # a child sees which plugin provides their timetable, not the other children's mapping
    assert client.get(BASE, params={"child_id": mia}, headers=mia_h).json()["plugin"]["name"] == "Fake School"
    # remove
    cleared = client.put(f"{BASE}/sources", headers=parent, json={"sources": [{"child_id": mia}]}).json()
    assert next(c for c in cleared["children"] if c["child_id"] == mia)["plugin_id"] is None


def test_free_identifier_when_the_plugin_lists_no_people(client, school):
    mia, _ = _user(client, "tp_mia", "child", "Mia")
    _, parent = _user(client, "tp_parent", "partner")
    school.people = []
    r = _map(client, parent, mia, person="any-id-123")
    assert r.status_code == 200
    assert next(c for c in r.json()["children"] if c["child_id"] == mia)["person_id"] == "any-id-123"


def test_week_merges_plugin_lessons_with_manual_entries(client, school):
    mia, mia_h = _user(client, "tp_mia", "child", "Mia")
    ben, _ = _user(client, "tp_ben", "child", "Ben")
    _, parent = _user(client, "tp_parent", "partner")
    _manual(client, parent, mia, "TP Manual Art", 0)                                   # school: replaced on Monday
    _manual(client, parent, mia, "TP Swimming", 0, kind="sport", start="16:00", end="17:00")  # stays
    _manual(client, parent, mia, "TP Saturday Art", 5)                                 # plugin has no Saturday
    _map(client, parent, mia, person="p1")
    monday = _monday()
    week = client.get(f"{BASE}/week", params={"child_id": mia, "start": (monday + timedelta(days=3)).isoformat()}, headers=mia_h).json()
    assert week["start"] == monday.isoformat() and week["plugin"]["status"] == "ok" and week["plugin"]["name"] == "Fake School"
    days = {d["weekday"]: d for d in week["days"]}
    assert [e["title"] for e in days[0]["entries"]] == ["Maths p1", "English", "TP Swimming"]
    assert days[0]["source"] == "plugin"
    assert all(e["title"] != "TP Manual Art" for e in days[0]["entries"])
    cancelled = days[1]["entries"][0]
    assert cancelled["status"] == "cancelled" and cancelled["note"] == "Teacher ill" and cancelled["period"] == 1
    assert cancelled["teacher"] == "Mr X" and cancelled["date"] == (monday + timedelta(days=1)).isoformat()
    assert days[2]["entries"][1]["status"] == "substitution"
    # weekend: no plugin data -> manual entries as before
    assert days[5]["source"] == "manual" and [e["title"] for e in days[5]["entries"]] == ["TP Saturday Art"]
    assert days[5]["entries"][0]["status"] == "normal"
    # the plugin was asked once for the whole week, with the mapped identifier
    child, start, end = school.calls[0]
    assert (child.id, child.name, child.person_id, start, end) == (mia, "Mia", "p1", monday, monday + timedelta(days=6))
    assert len(school.calls) == 1
    # another child without a mapping is not affected
    other = client.get(f"{BASE}/week", params={"child_id": ben, "start": monday.isoformat()}, headers=parent).json()
    assert other["plugin"] is None and all(d["source"] == "manual" for d in other["days"])


def test_holiday_day_without_plugin_data_falls_back_to_manual(client, school):
    mia, _ = _user(client, "tp_mia", "child", "Mia")
    _, parent = _user(client, "tp_parent", "partner")
    _manual(client, parent, mia, "TP Manual Wed", 2)
    _map(client, parent, mia)
    monday = _monday()
    school.skip = {(monday + timedelta(days=2)).isoformat()}
    week = client.get(f"{BASE}/week", params={"child_id": mia, "start": monday.isoformat()}, headers=parent).json()
    wed = week["days"][2]
    assert wed["source"] == "manual" and [e["title"] for e in wed["entries"]] == ["TP Manual Wed"]
    assert week["days"][1]["source"] == "plugin"


def test_today_card_carries_cancelled_lessons(client, school, monkeypatch):
    mia, mia_h = _user(client, "tp_mia", "child", "Mia")
    _, parent = _user(client, "tp_parent", "partner")
    _map(client, parent, mia)
    tuesday = date.today() + timedelta(days=(1 - date.today().weekday()) % 7)
    from app.services import timetable as svc

    with SessionLocal() as db:
        user = db.get(User, mia)
        card = asyncio.run(svc.today_card(db, user, tuesday))
    kid = card["children"][0]
    assert kid["source"] == "plugin" and kid["holiday"] is None
    assert [(e["title"], e["status"], e["period"]) for e in kid["entries"]] == [("Maths p1", "cancelled", 1), ("English", "normal", 2)]


def test_plugin_failure_falls_back_softly(client, school):
    mia, mia_h = _user(client, "tp_mia", "child", "Mia")
    _, parent = _user(client, "tp_parent", "partner")
    _manual(client, parent, mia, "TP Manual Mon", 0)
    _map(client, parent, mia)
    school.fail = True
    monday = _monday()
    r = client.get(f"{BASE}/week", params={"child_id": mia, "start": monday.isoformat()}, headers=mia_h)
    assert r.status_code == 200
    body = r.json()
    assert body["plugin"]["status"] == "unavailable" and "abc123" not in r.text
    assert [e["title"] for e in body["days"][0]["entries"]] == ["TP Manual Mon"]
    today = client.get(f"{BASE}/today", headers=mia_h)
    assert today.status_code == 200 and today.json()["status"] == "ok"


def test_plugin_timeout_and_removed_plugin(client, school, monkeypatch):
    mia, mia_h = _user(client, "tp_mia", "child", "Mia")
    _, parent = _user(client, "tp_parent", "partner")
    _map(client, parent, mia)
    monkeypatch.setattr(timetable_plugin, "PLUGIN_TIMEOUT", 0.2)
    school.hang = True
    body = client.get(f"{BASE}/week", params={"child_id": mia, "start": _monday().isoformat()}, headers=mia_h).json()
    assert body["plugin"]["status"] == "unavailable"
    school.hang = False
    plugin_registry.unregister("fakeschool")  # mapping stays, plugin gone
    body = client.get(f"{BASE}/week", params={"child_id": mia, "start": _monday().isoformat()}, headers=mia_h).json()
    assert body["plugin"]["status"] == "unavailable" and len(body["days"]) == 7
    plugin_registry.register(school)


def test_week_is_limited_to_visible_children(client, school):
    mia, mia_h = _user(client, "tp_mia", "child", "Mia")
    ben, _ = _user(client, "tp_ben", "child", "Ben")
    assert client.get(f"{BASE}/week", params={"child_id": ben}, headers=mia_h).status_code == 403
    assert client.get(f"{BASE}/week", params={"child_id": mia}, headers=mia_h).status_code == 200
