"""Erinnerungen „Wenn ich nach Hause komme“ (#26)."""

import pytest

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.notification_log import NotificationLog
from app.models.user import User

ARRIVED = "/api/reminders/arrived"


def _auth(client, name):
    with SessionLocal() as db:
        u = db.query(User).filter(User.username == name).first()
        if not u:
            u = User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"), role="partner")
            db.add(u)
            db.commit()
            db.refresh(u)
        uid = u.id
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}, uid


@pytest.fixture
def key(client, auth):
    r = client.post("/api/admin/service-keys", headers=auth, json={"name": "Home Assistant"})
    return {"Authorization": f"Bearer {r.json()['key']}"}


def _titles(uid):
    with SessionLocal() as db:
        return [n.body for n in db.query(NotificationLog).filter(NotificationLog.user_id == uid).order_by(NotificationLog.id)]


def test_arrival_reminder_has_no_time_and_is_not_fired_by_scheduler(client):
    import asyncio

    from app.services.scheduler import _tick

    h, uid = _auth(client, "ar_a")
    r = client.post("/api/reminders", headers=h, json={"title": "Pakete reinholen", "fire_on": "arrival"})
    assert r.status_code == 200
    assert r.json()["fire_on"] == "arrival" and r.json()["due_at"] is None
    asyncio.run(_tick())
    assert "Pakete reinholen" not in _titles(uid)


def test_arrival_rejects_time_and_recurrence_mix(client):
    h, _ = _auth(client, "ar_b")
    bad = client.post("/api/reminders", headers=h, json={"title": "x", "fire_on": "arrival", "due_at": "2026-10-15T09:00:00"})
    assert bad.status_code == 400
    assert client.post("/api/reminders", headers=h, json={"title": "x", "fire_on": "irgendwann"}).status_code == 422


def test_arrived_requires_service_key(client, auth):
    assert client.post(ARRIVED, json={"user": "admin"}).status_code == 401
    assert client.post(ARRIVED, json={"user": "admin"}, headers=auth).status_code == 401


def test_arrived_fires_own_reminders_once(client, key):
    h, uid = _auth(client, "ar_c")
    other_h, other_uid = _auth(client, "ar_d")
    client.post("/api/reminders", headers=h, json={"title": "Wäsche aufhängen", "fire_on": "arrival"})
    client.post("/api/reminders", headers=other_h, json={"title": "Nicht meins", "fire_on": "arrival"})
    client.post("/api/reminders", headers=h, json={"title": "Zeit-Erinnerung", "due_at": "2026-10-15T09:00:00"})

    r = client.post(ARRIVED, headers=key, json={"user": "AR_C"})
    assert r.status_code == 200 and r.json()["fired"] == ["Wäsche aufhängen"]
    assert "Wäsche aufhängen" in _titles(uid) and "Nicht meins" not in _titles(uid)
    assert "Wäsche aufhängen" not in _titles(other_uid)
    # zweite Ankunft: schon ausgelöst → nichts mehr
    assert client.post(ARRIVED, headers=key, json={"user": "ar_c"}).json()["fired"] == []


def test_family_arrival_goes_to_first_person_home(client, key):
    h, _ = _auth(client, "ar_e")
    _, f_uid = _auth(client, "ar_f")
    client.post("/api/reminders", headers=h, json={"title": "Briefkasten leeren", "fire_on": "arrival", "for_family": True})
    assert client.post(ARRIVED, headers=key, json={"user": "ar_f"}).json()["fired"] == ["Briefkasten leeren"]
    assert "Briefkasten leeren" in _titles(f_uid)
    assert client.post(ARRIVED, headers=key, json={"user": "ar_e"}).json()["fired"] == []


def test_recurring_arrival_rearms_after_done(client, key):
    h, uid = _auth(client, "ar_g")
    rid = client.post("/api/reminders", headers=h, json={
        "title": "Schuhe aus", "fire_on": "arrival", "recurrence": "daily"}).json()["id"]
    assert client.post(ARRIVED, headers=key, json={"user": "ar_g"}).json()["fired"] == ["Schuhe aus"]
    done = client.patch(f"/api/reminders/{rid}", headers=h, json={"completed": True}).json()
    assert done["completed"] is False and done["due_at"] is None  # wieder scharf für die nächste Ankunft
    assert client.post(ARRIVED, headers=key, json={"user": "ar_g"}).json()["fired"] == ["Schuhe aus"]
    once = client.post("/api/reminders", headers=h, json={"title": "Einmalig", "fire_on": "arrival"}).json()["id"]
    assert client.patch(f"/api/reminders/{once}", headers=h, json={"completed": True}).json()["completed"] is True


def test_unknown_user_is_404(client, key):
    assert client.post(ARRIVED, headers=key, json={"user": "niemand"}).status_code == 404
