"""Birthdays and anniversaries: dates, calendar, Today, reminders, gift ideas and who may see what."""

import asyncio
from datetime import date, datetime, timedelta

import pytest

from app.core.database import SessionLocal
from app.core.timeutil import local_tz
from app.core.security import get_password_hash
from app.models.birthday import Birthday, GiftIdea
from app.models.event_alarm import EventAlarmSent
from app.models.user import User
from app.services import birthdays as svc

B = "/api/birthdays"


def _today():
    """The hub's local date (the container clock may be on another day around midnight)."""
    return datetime.now(local_tz()).date()


@pytest.fixture(autouse=True)
def _clean():
    with SessionLocal() as db:
        db.query(GiftIdea).delete()
        db.query(Birthday).delete()
        db.query(EventAlarmSent).filter(EventAlarmSent.key.like("birthday|%")).delete(synchronize_session=False)
        db.commit()
    yield


def _login(client, name, role="partner"):
    with SessionLocal() as db:
        u = db.query(User).filter(User.username == name).first()
        if not u:
            u = User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"), role=role)
            db.add(u)
            db.commit()
            db.refresh(u)
        uid = u.id
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}, uid


def _add(client, h, **kw):
    body = {"name": "Oma", "month": 3, "day": 14, "year": 1946, **kw}
    r = client.post(B, headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


# --- pure date logic ---


def test_leap_day_falls_back_to_28_february():
    assert svc.occurrence_in(2027, 2, 29) == date(2027, 2, 28)
    assert svc.occurrence_in(2028, 2, 29) == date(2028, 2, 29)
    assert svc.next_occurrence(2, 29, date(2027, 3, 1)) == date(2028, 2, 29)
    assert svc.next_occurrence(2, 29, date(2027, 2, 28)) == date(2027, 2, 28)


def test_valid_date_rules():
    assert svc.valid_date(2, 29) and svc.valid_date(2, 29, 2000) and not svc.valid_date(2, 29, 2001)
    assert not svc.valid_date(4, 31) and not svc.valid_date(13, 1) and svc.valid_date(12, 31, 1990)


def test_age_only_with_year():
    assert svc.age_on(1946, date(2026, 3, 14)) == 80
    assert svc.age_on(None, date(2026, 3, 14)) is None
    assert svc.age_on(2030, date(2026, 3, 14)) is None


# --- API ---


def test_create_list_with_age_and_validation(client):
    h, _ = _login(client, "bd_p1")
    today = _today() + timedelta(days=3)
    item = _add(client, h, name="Oma", month=today.month, day=today.day, year=today.year - 80)
    assert item["days_until"] == 3 and item["turns"] == 80 and item["gift_count"] == 0
    _add(client, h, name="Opa", month=today.month, day=today.day, year=None)
    rows = client.get(B, headers=h).json()
    assert {r["name"]: r["turns"] for r in rows} == {"Oma": 80, "Opa": None}
    bad = client.post(B, headers=h, json={"name": "X", "month": 2, "day": 30})
    assert bad.status_code == 422
    assert client.post(B, headers=h, json={"name": "X", "month": 2, "day": 29, "year": 2001}).status_code == 422
    assert client.post(B, headers=h, json={"name": "Y", "month": 2, "day": 29}).status_code == 201


def test_edit_and_delete_remove_gifts(client):
    h, _ = _login(client, "bd_p2")
    b = _add(client, h)
    client.post(f"{B}/{b['id']}/gifts", headers=h, json={"text": "Buch"})
    r = client.put(f"{B}/{b['id']}", headers=h, json={"name": "Oma Erna", "month": 3, "day": 15, "remind_days_before": None})
    assert r.status_code == 200 and r.json()["name"] == "Oma Erna" and r.json()["remind_days_before"] is None
    assert client.delete(f"{B}/{b['id']}", headers=h).status_code == 204
    with SessionLocal() as db:
        assert db.query(GiftIdea).count() == 0


def test_roles(client):
    partner, _ = _login(client, "bd_p3")
    child, _ = _login(client, "bd_child", "child")
    guest, _ = _login(client, "bd_guest", "guest")
    b = _add(client, partner)
    # guests: nothing
    assert client.get(B, headers=guest).status_code == 403
    assert client.get(f"{B}/{b['id']}/gifts", headers=guest).status_code == 403
    # children: read + gift ideas, no entry management
    assert client.get(B, headers=child).status_code == 200
    assert client.post(B, headers=child, json={"name": "Z", "month": 1, "day": 1}).status_code == 403
    assert client.put(f"{B}/{b['id']}", headers=child, json={"name": "Z", "month": 1, "day": 1}).status_code == 403
    assert client.delete(f"{B}/{b['id']}", headers=child).status_code == 403
    mine = client.post(f"{B}/{b['id']}/gifts", headers=child, json={"text": "Zeichnung"}).json()
    theirs = client.post(f"{B}/{b['id']}/gifts", headers=partner, json={"text": "Schal"}).json()
    assert client.patch(f"{B}/{b['id']}/gifts/{theirs['id']}", headers=child, json={"done": True}).status_code == 200
    assert client.patch(f"{B}/{b['id']}/gifts/{theirs['id']}", headers=child, json={"text": "x"}).status_code == 403
    assert client.delete(f"{B}/{b['id']}/gifts/{theirs['id']}", headers=child).status_code == 403
    assert client.delete(f"{B}/{b['id']}/gifts/{mine['id']}", headers=child).status_code == 204
    assert client.delete(f"{B}/{b['id']}/gifts/{theirs['id']}", headers=partner).status_code == 204


def test_gift_ideas_hidden_from_the_linked_person(client):
    owner, _ = _login(client, "bd_p4")
    mama, mama_id = _login(client, "bd_mama")
    admin, admin_id = _login(client, "bd_admin_linked", "admin")
    b = _add(client, owner, name="Mama", user_id=mama_id)
    g = client.post(f"{B}/{b['id']}/gifts", headers=owner, json={"text": "Parfum", "link": "https://example.org/p"}).json()
    # everyone else sees them, with the count
    assert [x["text"] for x in client.get(f"{B}/{b['id']}/gifts", headers=owner).json()] == ["Parfum"]
    assert client.get(B, headers=owner).json()[0]["gift_count"] == 1
    # the linked person: no list, no add, no change, no delete, no count; 404 as if nothing existed
    assert client.get(f"{B}/{b['id']}/gifts", headers=mama).status_code == 404
    assert client.post(f"{B}/{b['id']}/gifts", headers=mama, json={"text": "x"}).status_code == 404
    assert client.patch(f"{B}/{b['id']}/gifts/{g['id']}", headers=mama, json={"done": True}).status_code == 404
    assert client.delete(f"{B}/{b['id']}/gifts/{g['id']}", headers=mama).status_code == 404
    own = client.get(B, headers=mama).json()[0]
    assert own["is_you"] is True and own["gift_count"] is None and "gift" not in str(own.get("name", "")).lower()
    # the rule holds for admins who are the linked person as well
    b2 = _add(client, owner, name="Admin", user_id=admin_id)
    assert client.get(f"{B}/{b2['id']}/gifts", headers=admin).status_code == 404
    # ideas never leak into the calendar or Today
    assert "Parfum" not in str(client.get(f"/api/calendar/events?days=30&start={_today().isoformat()}", headers=mama).json())
    assert "Parfum" not in str(client.get("/api/today", headers=mama).json())
    assert client.post(B, headers=owner, json={"name": "X", "month": 1, "day": 1, "user_id": 999999}).status_code == 422
    with SessionLocal() as db:  # do not leave an extra admin behind: other tests count admins
        db.query(GiftIdea).delete()
        db.query(Birthday).delete()
        db.query(User).filter(User.id == admin_id).delete()
        db.commit()


def test_gift_link_must_be_http(client):
    h, _ = _login(client, "bd_p5")
    b = _add(client, h)
    assert client.post(f"{B}/{b['id']}/gifts", headers=h, json={"text": "x", "link": "javascript:alert(1)"}).status_code == 422


# --- calendar and Today ---


def test_virtual_calendar_events_and_chip(client):
    h, _ = _login(client, "bd_p6")
    guest, _ = _login(client, "bd_guest2", "guest")
    cals = client.get("/api/calendar/calendars", headers=h).json()
    assert not [c for c in cals if c["source"] == "birthdays"]  # no chip while empty
    d = _today() + timedelta(days=2)
    _add(client, h, name="Oma", month=d.month, day=d.day, year=d.year - 80)
    cals = client.get("/api/calendar/calendars", headers=h).json()
    chip = [c for c in cals if c["id"] == "birthdays"]
    assert chip and chip[0]["writable"] is False and chip[0]["source"] == "birthdays"
    evs = [e for e in client.get(f"/api/calendar/events?days=10&start={_today().isoformat()}", headers=h).json()
           if e["source"] == "birthdays"]
    assert len(evs) == 1 and evs[0]["all_day"] and evs[0]["title"] == "🎂 Oma (80)" and evs[0]["start"] == d.isoformat()
    assert not [e for e in client.get(f"/api/calendar/events?days=10&start={_today().isoformat()}", headers=guest).json()
                if e["source"] == "birthdays"]
    assert not [c for c in client.get("/api/calendar/calendars", headers=guest).json() if c["id"] == "birthdays"]


def test_today_card_data(client):
    h, uid = _login(client, "bd_p7")
    d = _today() + timedelta(days=3)
    far = _today() + timedelta(days=100)
    _add(client, h, name="Oma", month=d.month, day=d.day, year=d.year - 80)
    _add(client, h, name="Fern", month=far.month, day=far.day)
    items = client.get("/api/today", headers=h).json()["birthdays"]
    assert [(i["name"], i["days_until"], i["turns"]) for i in items] == [("Oma", 3, 80)]
    guest, _ = _login(client, "bd_guest3", "guest")
    assert client.get("/api/today", headers=guest).json()["birthdays"] == []
    # not duplicated in the events card
    assert all(e["title"] != "🎂 Oma (80)" for e in client.get("/api/today", headers=h).json()["events"])


def test_today_layout_knows_the_birthdays_card(client):
    h, _ = _login(client, "bd_p8")
    ids = [c["id"] for c in client.get("/api/me/today-layout", headers=h).json()["cards"]]
    assert "birthdays" in ids


# --- reminders ---


def _sent(monkeypatch):
    calls = []

    async def fake(user_id, title, body, data=None, category="info", source="hub", silent=False):
        calls.append((user_id, title, body))
        return 1

    monkeypatch.setattr("app.services.notify.notify", fake)
    return calls


def test_reminder_days_before_once_and_not_for_the_linked_person(client, monkeypatch):
    h, _ = _login(client, "bd_p9")
    _, mama_id = _login(client, "bd_mama2")
    _, guest_id = _login(client, "bd_guest4", "guest")
    day = _today() + timedelta(days=7)
    _add(client, h, name="Mama", month=day.month, day=day.day, year=day.year - 50, user_id=mama_id, remind_days_before=7)
    _add(client, h, name="Spaeter", month=day.month, day=day.day, remind_days_before=3)
    calls = _sent(monkeypatch)
    noon = datetime.combine(_today(), datetime.min.time()).replace(hour=12)
    n = asyncio.run(svc.send_due(noon))
    users = {c[0] for c in calls}
    assert n == len(calls) > 0 and mama_id not in users and guest_id not in users
    assert all(c[1] == "🎂 Mama" for c in calls) and "in 7 Tagen · wird 50" in calls[0][2]
    assert asyncio.run(svc.send_due(noon)) == 0  # once per person and occurrence
    early = noon.replace(hour=6)
    with SessionLocal() as db:
        db.query(EventAlarmSent).filter(EventAlarmSent.key.like("birthday|%")).delete(synchronize_session=False)
        db.commit()
    assert asyncio.run(svc.send_due(early)) == 0  # not before 08:00


def test_reminder_message_texts():
    row = Birthday(name="Oma", kind="birthday", month=3, day=14, year=1946)
    assert svc.message(row, date(2026, 3, 14), 0) == ("🎂 Oma", "Geburtstag heute · wird 80")
    assert svc.message(row, date(2026, 3, 14), 1)[1] == "Geburtstag morgen · wird 80"
    ann = Birthday(name="Anna & Tom", kind="anniversary", month=5, day=2, year=None)
    assert svc.message(ann, date(2026, 5, 2), 5) == ("💍 Anna & Tom", "Jahrestag in 5 Tagen")
