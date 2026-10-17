"""Benachrichtigungs-Zentrale (#21) und Verlauf (#23)."""

from datetime import time

import pytest

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.notification_log import NotificationLog
from app.models.notification_prefs import NotificationPreference
from app.models.user import User


def _user(name, admin=False):
    with SessionLocal() as db:
        u = db.query(User).filter(User.username == name).first()
        if not u:
            u = User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"),
                     role="admin" if admin else "partner", is_admin=admin)
            db.add(u)
            db.commit()
            db.refresh(u)
        return u


def _auth(client, name, admin=False):
    _user(name, admin)
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def key(client, auth):
    r = client.post("/api/admin/service-keys", headers=auth, json={"name": "Home Assistant"})
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['key']}"}, r.json()["id"]


@pytest.fixture
def sent(monkeypatch):
    """Push-Versand abfangen; Verlauf läuft echt."""
    from app.services import notify as notify_module

    calls = []

    async def fake_fcm(self, db, device, title, body, data, category):
        calls.append((device.user_id, title, category, data))
        return True

    monkeypatch.setattr(notify_module.NotifyService, "fcm_configured", property(lambda self: True))
    monkeypatch.setattr(notify_module.NotifyService, "_send_fcm", fake_fcm)
    return calls


def _device(user):
    from app.models.push_device import PushDevice

    with SessionLocal() as db:
        if not db.query(PushDevice).filter(PushDevice.user_id == user.id).first():
            db.add(PushDevice(user_id=user.id, kind="fcm", token=f"tok-{user.username}", device_name="Test"))
            db.commit()


def test_notify_requires_service_key(client, auth):
    body = {"title": "Waschmaschine fertig"}
    assert client.post("/api/notify", json=body).status_code == 401
    assert client.post("/api/notify", json=body, headers=auth).status_code == 401  # Nutzer-Token reicht nicht
    assert client.post("/api/notify", json=body, headers={"Authorization": "Bearer fhs_falsch"}).status_code == 401


def test_notify_named_recipient_gets_push_and_history(client, key, sent):
    headers, _ = key
    anna = _user("nc_anna")
    _device(anna)
    r = client.post("/api/notify", headers=headers, json={
        "title": "Waschmaschine fertig", "body": "Bitte ausräumen", "to": ["NC_Anna"], "category": "house", "route": "/today"})
    assert r.status_code == 200
    assert r.json() == {"recipients": ["nc_anna"], "delivered": 1}
    assert sent[-1][0] == anna.id and sent[-1][2] == "house" and sent[-1][3]["route"] == "/today"
    with SessionLocal() as db:
        log = db.query(NotificationLog).filter(NotificationLog.user_id == anna.id).order_by(NotificationLog.id.desc()).first()
        assert (log.title, log.source, log.category, log.delivered, log.suppressed) == (
            "Waschmaschine fertig", "Home Assistant", "house", 1, False)


def test_notify_family_reaches_all_active_users(client, key, sent):
    headers, _ = key
    with SessionLocal() as db:
        active = {u.username for u in db.query(User).filter(User.is_active == True).all()}  # noqa: E712
    r = client.post("/api/notify", headers=headers, json={"title": "Müll morgen", "to": "family", "category": "house"})
    assert set(r.json()["recipients"]) == active


def test_notify_rejects_unknown_recipient_and_category(client, key):
    headers, _ = key
    r = client.post("/api/notify", headers=headers, json={"title": "x", "to": ["niemand"]})
    assert r.status_code == 422 and r.json()["detail"]["names"] == ["niemand"]
    r = client.post("/api/notify", headers=headers, json={"title": "x", "category": "werbung"})
    assert r.status_code == 422 and "house" in r.json()["detail"]["allowed"]


def test_quiet_hours_suppress_push_but_keep_history(client, key, sent):
    headers, _ = key
    ben = _user("nc_ben")
    _device(ben)
    with SessionLocal() as db:
        db.add(NotificationPreference(user_id=ben.id, category="house", enabled=True,
                                      quiet_start=time(0, 0), quiet_end=time(23, 59)))
        db.commit()
    before = len(sent)
    r = client.post("/api/notify", headers=headers, json={"title": "Fenster offen", "to": ["nc_ben"], "category": "house"})
    assert r.json()["delivered"] == 0 and len(sent) == before
    h = _auth(client, "nc_ben")
    items = client.get("/api/me/notifications", headers=h).json()["items"]
    assert items[0]["title"] == "Fenster offen" and items[0]["pushed"] is False


def test_history_read_flow_and_privacy(client, key, sent):
    headers, _ = key
    _user("nc_cleo")
    client.post("/api/notify", headers=headers, json={"title": "Eins", "to": ["nc_cleo"], "category": "system"})
    client.post("/api/notify", headers=headers, json={"title": "Zwei", "to": ["nc_cleo"], "category": "system"})
    cleo = _auth(client, "nc_cleo")
    other = _auth(client, "nc_dora")
    data = client.get("/api/me/notifications", headers=cleo).json()
    assert data["unread"] == 2 and [i["title"] for i in data["items"]] == ["Zwei", "Eins"]
    assert client.get("/api/me/notifications", headers=other).json()["items"] == []
    assert client.get("/api/today", headers=cleo).json()["notifications_unread"] == 2

    first_id = data["items"][1]["id"]
    # fremde IDs werden nicht markiert
    assert client.post("/api/me/notifications/read", headers=other, json={"ids": [first_id]}).json()["marked"] == 0
    assert client.post("/api/me/notifications/read", headers=cleo, json={"ids": [first_id]}).json()["marked"] == 1
    assert client.get("/api/me/notifications", headers=cleo).json()["unread"] == 1
    assert client.post("/api/me/notifications/read", headers=cleo, json={}).json()["marked"] == 1
    assert client.get("/api/me/notifications", headers=cleo).json()["unread"] == 0


def test_internal_notify_also_lands_in_history(sent):
    import asyncio

    from app.services.notify import notify

    eve = _user("nc_eve")
    asyncio.run(notify(eve.id, "Neue Aufgabe zugewiesen", "Anna: Müll", data={"route": "/tasks"}, category="task_assigned"))
    with SessionLocal() as db:
        log = db.query(NotificationLog).filter(NotificationLog.user_id == eve.id).one()
        assert (log.source, log.route, log.category) == ("hub", "/tasks", "task_assigned")


def test_service_key_admin_only_and_revocable(client, auth, key):
    headers, key_id = key
    partner = _auth(client, "nc_fred")
    assert client.get("/api/admin/service-keys", headers=partner).status_code == 403
    assert client.post("/api/admin/service-keys", headers=partner, json={"name": "x"}).status_code == 403
    listed = client.get("/api/admin/service-keys", headers=auth).json()
    assert any(k["id"] == key_id and "key" not in k for k in listed)
    assert client.delete(f"/api/admin/service-keys/{key_id}", headers=auth).status_code == 204
    assert client.post("/api/notify", headers=headers, json={"title": "x", "to": "admins"}).status_code == 401


def test_silent_goes_to_history_only(client, key, sent):
    headers, _ = key
    gina = _user("nc_gina")
    _device(gina)
    before = len(sent)
    r = client.post("/api/notify", headers=headers, json={
        "title": "🧺 Waschmaschine fertig", "to": ["nc_gina"], "category": "house", "silent": True})
    assert r.json()["delivered"] == 0 and len(sent) == before
    items = client.get("/api/me/notifications", headers=_auth(client, "nc_gina")).json()["items"]
    assert items[0]["title"] == "🧺 Waschmaschine fertig" and items[0]["pushed"] is False
