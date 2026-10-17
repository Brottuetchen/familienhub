"""Shelfarr-Webhook → Hub-Mitteilungen (#22)."""

import pytest

from app.config import settings
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.notification_log import NotificationLog
from app.models.user import User

URL = "/api/books/webhook"


def _user(name):
    with SessionLocal() as db:
        u = db.query(User).filter(User.username == name).first()
        if not u:
            u = User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"), role="partner")
            db.add(u)
            db.commit()
            db.refresh(u)
        return u


def _payload(event, username, title="Momo", book_type="audiobook", message="Shelfarr-Text"):
    return {
        "event": event, "title": f"Shelfarr: {event}", "message": message, "occurred_at": "2026-10-14T18:00:00+02:00",
        "request": {"id": 7, "status": "completed", "attention_needed": False},
        "book": {"id": 3, "title": title, "author": "Michael Ende", "book_type": book_type},
        "user": {"id": 2, "username": username},
    }


@pytest.fixture
def key(client, auth):
    r = client.post("/api/admin/service-keys", headers=auth, json={"name": "Shelfarr"})
    return {"Authorization": f"Bearer {r.json()['key']}"}


def _last(user_id):
    with SessionLocal() as db:
        return db.query(NotificationLog).filter(NotificationLog.user_id == user_id).order_by(NotificationLog.id.desc()).first()


def test_webhook_requires_service_key(client, auth):
    assert client.post(URL, json=_payload("request_completed", "x")).status_code == 401
    assert client.post(URL, json=_payload("request_completed", "x"), headers=auth).status_code == 401


def test_completed_goes_to_requester_only(client, key):
    lena = _user("sh_lena")
    r = client.post(URL, headers=key, json=_payload("request_completed", "SH_Lena"))
    assert r.status_code == 200 and r.json()["recipients"] == ["sh_lena"]
    log = _last(lena.id)
    assert log.title == "📚 „Momo“ ist da"
    assert log.body == "Hörbuch von Michael Ende liegt in der Bibliothek."
    assert (log.category, log.route, log.source) == ("media", "/books", "Shelfarr")


def test_user_map_is_applied_in_reverse(client, key, monkeypatch):
    monkeypatch.setattr(settings, "shelfarr_user_map", "sh_mia=mia_buecher")
    mia = _user("sh_mia")
    r = client.post(URL, headers=key, json=_payload("request_completed", "mia_buecher", book_type="ebook"))
    assert r.json()["recipients"] == ["sh_mia"]
    assert _last(mia.id).body == "E-Book von Michael Ende liegt in der Bibliothek."


def test_failed_reaches_requester_and_admins(client, key):
    _user("sh_tom")
    r = client.post(URL, headers=key, json=_payload("request_failed", "sh_tom", message="Kein Treffer"))
    assert r.json()["recipients"] == ["sh_tom", "admin"]
    log = _last(_user("sh_tom").id)
    assert log.title == "📚 „Momo“ hat nicht geklappt" and log.body == "Kein Treffer"


def test_unknown_shelfarr_user_falls_back_to_admins(client, key):
    r = client.post(URL, headers=key, json=_payload("request_attention", "gibtsnicht"))
    assert r.json()["recipients"] == ["admin"]


def test_created_is_ignored_and_test_reaches_admins(client, key):
    r = client.post(URL, headers=key, json=_payload("request_created", "sh_lena"))
    assert r.status_code == 200 and r.json() == {"ignored": "request_created"}
    r = client.post(URL, headers=key, json={"event": "test", "title": "Shelfarr Test", "message": "Test notification from Shelfarr"})
    assert r.json()["recipients"] == ["admin"]
    assert _last(_user("admin").id).category == "system"
