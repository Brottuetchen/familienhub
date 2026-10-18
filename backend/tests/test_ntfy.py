"""ntfy as a per-person push channel (#23): the admin picks the server, each person gets a secret topic."""

import json

import httpx
import pytest
import respx

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User

NTFY = "https://ntfy.example.test"


def _auth(client, name, role="partner"):
    with SessionLocal() as db:
        if not db.query(User).filter(User.username == name).first():
            db.add(User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"), role=role))
            db.commit()
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def ntfy_on(monkeypatch):
    from app.services import config_store

    monkeypatch.setitem(config_store._extra, "NTFY_URL", NTFY)
    monkeypatch.setitem(config_store._extra, "NTFY_TOKEN", "tk_publisher")
    monkeypatch.setitem(config_store._extra, "HUB_PUBLIC_URL", "https://hub.example.test")


def test_not_available_without_server(client):
    h = _auth(client, "ntfy_none")
    r = client.get("/api/me/ntfy", headers=h)
    assert r.status_code == 200
    assert r.json()["available"] is False
    assert client.put("/api/me/ntfy", headers=h, json={"enabled": True}).status_code == 409


def test_enable_generates_secret_topic_and_subscribe_url(client, ntfy_on):
    h = _auth(client, "ntfy_anna")
    r = client.put("/api/me/ntfy", headers=h, json={"enabled": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["available"] is True and body["enabled"] is True
    assert body["server"] == NTFY
    topic = body["topic"]
    assert topic.startswith("fh_") and len(topic) >= 20
    assert body["subscribe_url"] == f"{NTFY}/{topic}"
    # the publisher token never leaves the server
    assert "tk_publisher" not in r.text
    # stays the same on reload, changes only on request
    assert client.get("/api/me/ntfy", headers=h).json()["topic"] == topic
    new = client.post("/api/me/ntfy/new-topic", headers=h).json()["topic"]
    assert new != topic and new.startswith("fh_")


@pytest.mark.parametrize("topic", ["kurz", "mit leerzeichen 123", "../../etc/passwd", "x" * 80])
def test_own_topic_is_validated(client, ntfy_on, topic):
    h = _auth(client, "ntfy_val")
    assert client.put("/api/me/ntfy", headers=h, json={"enabled": True, "topic": topic}).status_code == 422


def test_topics_are_unique_per_person(client, ntfy_on):
    a, b = _auth(client, "ntfy_u1"), _auth(client, "ntfy_u2")
    assert client.put("/api/me/ntfy", headers=a, json={"enabled": True, "topic": "fh_gemeinsam_123"}).status_code == 200
    assert client.put("/api/me/ntfy", headers=b, json={"enabled": True, "topic": "fh_gemeinsam_123"}).status_code == 409


def test_notify_publishes_to_ntfy_with_token_click_and_actions(client, ntfy_on):
    from app.services.notify import notify

    h = _auth(client, "ntfy_ben")
    topic = client.put("/api/me/ntfy", headers=h, json={"enabled": True}).json()["topic"]
    with SessionLocal() as db:
        uid = db.query(User).filter(User.username == "ntfy_ben").first().id

    with respx.mock(using="httpx") as http:
        route = http.post(f"{NTFY}/").mock(return_value=httpx.Response(200, json={"id": "x"}))
        import asyncio

        delivered = asyncio.run(notify(uid, "⏰ Erinnerung", "Müll raus", category="reminder", data={
            "route": "/reminders", "reminder_id": 7, "actions": "done,snooze_1h", "action_token": "signed-token"}))
    assert delivered == 1
    req = route.calls.last.request
    assert req.headers["Authorization"] == "Bearer tk_publisher"
    msg = json.loads(req.content)
    assert msg["topic"] == topic
    assert msg["title"] == "⏰ Erinnerung" and msg["message"] == "Müll raus"
    assert msg["click"] == "https://hub.example.test/"
    labels = [a["label"] for a in msg["actions"]]
    assert labels == ["Erledigt", "In 1 Std."]
    first = msg["actions"][0]
    assert first["action"] == "http" and first["method"] == "POST"
    assert first["url"] == "https://hub.example.test/api/reminders/7/action"
    assert json.loads(first["body"]) == {"action": "done", "token": "signed-token"}


def test_disabled_or_quiet_means_no_ntfy(client, ntfy_on):
    from app.services.notify import notify

    h = _auth(client, "ntfy_off")
    client.put("/api/me/ntfy", headers=h, json={"enabled": False})
    with SessionLocal() as db:
        uid = db.query(User).filter(User.username == "ntfy_off").first().id
    with respx.mock(using="httpx", assert_all_called=False) as http:
        route = http.post(f"{NTFY}/").mock(return_value=httpx.Response(200))
        import asyncio

        assert asyncio.run(notify(uid, "Test", "x", category="system")) == 0
    assert not route.called


def test_ntfy_error_is_logged_not_raised(client, ntfy_on):
    from app.services.notify import notify

    h = _auth(client, "ntfy_err")
    client.put("/api/me/ntfy", headers=h, json={"enabled": True})
    with SessionLocal() as db:
        uid = db.query(User).filter(User.username == "ntfy_err").first().id
    with respx.mock(using="httpx") as http:
        http.post(f"{NTFY}/").mock(return_value=httpx.Response(403, json={"error": "forbidden"}))
        import asyncio

        assert asyncio.run(notify(uid, "Test", "x", category="system")) == 0


def test_delete_removes_target(client, ntfy_on):
    h = _auth(client, "ntfy_del")
    client.put("/api/me/ntfy", headers=h, json={"enabled": True})
    assert client.delete("/api/me/ntfy", headers=h).status_code == 204
    body = client.get("/api/me/ntfy", headers=h).json()
    assert body["enabled"] is False and body["topic"] is None


def test_guest_may_use_ntfy(client, ntfy_on):
    h = _auth(client, "ntfy_gast", role="guest")
    assert client.put("/api/me/ntfy", headers=h, json={"enabled": True}).status_code == 200
