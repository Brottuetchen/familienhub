"""Feedback aus der App und App-Fehler ins Protokoll."""

import logging

from app.core import log_buffer
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User
from app.routers import feedback as fb_router


def _partner(client, name="fb_carla"):
    with SessionLocal() as db:
        if not db.query(User).filter(User.username == name).first():
            db.add(User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"), role="partner"))
            db.commit()
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_feedback_reaches_admins(client, auth, monkeypatch):
    sent = []

    async def fake_notify(user_id, title, body, **kw):
        sent.append((title, body))

    monkeypatch.setattr(fb_router, "notify", fake_notify)
    h = _partner(client)
    r = client.post("/api/feedback", headers=h, json={"text": "Einkauf lädt langsam", "area": "Einkauf",
                                                      "app_version": "1.0.0+420", "platform": "android"})
    assert r.status_code == 201
    assert sent and sent[0][0].startswith("💬 Feedback von") and "Einkauf lädt langsam" in sent[0][1]
    items = client.get("/api/admin/feedback", headers=auth).json()["items"]
    mine = next(i for i in items if i["id"] == r.json()["id"])
    assert mine["area"] == "Einkauf" and mine["platform"] == "android" and mine["done"] is False
    assert client.post(f"/api/admin/feedback/{mine['id']}/done", headers=auth).json() == {"done": True}
    assert client.get("/api/admin/feedback", headers=h).status_code == 403


def test_feedback_validation(client):
    h = _partner(client, "fb_kurz")
    assert client.post("/api/feedback", headers=h, json={"text": "x"}).status_code == 422
    assert client.post("/api/feedback", json={"text": "ohne Anmeldung"}).status_code == 401


def test_client_errors_go_to_protocol_redacted_and_limited(client, auth):
    log_buffer.clear()
    fb_router._recent.clear()
    h = _partner(client, "fb_fehler")
    r = client.post("/api/client-errors", headers=h, json={
        "message": "Null check operator token=geheim123", "platform": "ios", "app_version": "1.0.0+420",
        "stack": "#0 dart:core\n#1 package:familienhub/screens/today/today_screen.dart:42"})
    assert r.json() == {"accepted": True}
    entries = client.get("/api/admin/log", headers=auth).json()["items"]
    e = next(x for x in entries if x["source"] == "familienhub.app")
    assert "today_screen.dart:42" in e["message"] and "ios" in e["message"] and "geheim123" not in e["message"]
    for _ in range(fb_router.MAX_PER_HOUR):
        client.post("/api/client-errors", headers=h, json={"message": "Schleife"})
    assert client.post("/api/client-errors", headers=h, json={"message": "zu viel"}).json() == {"accepted": False}
    assert logging.getLogger("familienhub.app")  # Logger existiert
