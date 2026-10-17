"""Sicherheitskorrekturen Aufgaben: CalDAV-Adresse (SSRF), Zuweisung, keine internen Fehlertexte."""

import pytest

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User

CALDAV = "/api/tasks/me/caldav"


def _auth(client, name, role="partner", active=True):
    with SessionLocal() as db:
        u = db.query(User).filter(User.username == name).first()
        if not u:
            u = User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"),
                     role=role, is_active=active)
            db.add(u)
            db.commit()
            db.refresh(u)
        uid = u.id
    if not active:
        return None, uid
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}, uid


def _put(client, h, url):
    return client.put(CALDAV, headers=h, json={"url": url, "username": "u", "password": "p"})


@pytest.mark.parametrize("url", [
    "http://cloud.example.com/remote.php/dav",       # kein https
    "https://192.168.1.82:8123/api/states",       # IP-Adresse (Heimnetz)
    "https://127.0.0.1/remote.php/dav",
    "https://[::1]/remote.php/dav",
    "https://localhost/remote.php/dav",
    "https://user:pw@cloud.example.com/remote.php/dav",  # Zugangsdaten in der URL
    "file:///etc/passwd",
    "https://cloud.example.com/dav?x=1",
    "nicht-mal-eine-url",
])
def test_caldav_rejects_internal_or_odd_urls(client, url, monkeypatch):
    monkeypatch.setenv("CALDAV_URL", "")
    h, _ = _auth(client, "sec_a")
    r = _put(client, h, url)
    assert r.status_code == 422, (url, r.text)


def test_caldav_accepts_public_https(client, monkeypatch):
    monkeypatch.setenv("CALDAV_URL", "")
    h, _ = _auth(client, "sec_b")
    assert _put(client, h, "https://cloud.example.com/remote.php/dav").status_code == 200


def test_caldav_pinned_to_configured_server(client, monkeypatch):
    """Ist CALDAV_URL gesetzt, sind nur Adressen auf genau diesem Server erlaubt (auch interne mit http)."""
    from app.config import settings

    monkeypatch.setattr(settings, "caldav_url", "http://nextcloud.lan:8080/remote.php/dav")
    h, _ = _auth(client, "sec_c")
    assert _put(client, h, "http://nextcloud.lan:8080/remote.php/dav/calendars/c/").status_code == 200
    assert _put(client, h, "http://nextcloud.lan:9999/remote.php/dav").status_code == 422
    assert _put(client, h, "https://cloud.example.com/remote.php/dav").status_code == 422


def test_task_list_kind_is_validated(client):
    h, _ = _auth(client, "sec_d")
    r = client.put("/api/tasks/me/task-lists", headers=h, json=[{"caldav_url": "https://c/x", "kind": "admin"}])
    assert r.status_code == 422


def test_assignee_must_be_active_household_member(client):
    h, _ = _auth(client, "sec_e")
    _, inactive = _auth(client, "sec_inactive", active=False)
    _, guest = _auth(client, "sec_guest", role="guest")
    for bad in (999999, inactive, guest):
        r = client.post("/api/tasks", headers=h, json={"title": "Müll", "assignee_id": bad})
        assert r.status_code == 422, (bad, r.text)


def test_internal_errors_are_not_echoed(client, monkeypatch):
    from app.connectors.nextcloud_tasks_connector import NextcloudTasksConnector

    async def boom(self, *a, **k):
        raise RuntimeError("psycopg2: password authentication failed for user hermes at 10.0.0.5")

    monkeypatch.setattr(NextcloudTasksConnector, "create_task", boom)
    h, _ = _auth(client, "sec_f")
    r = client.post("/api/tasks", headers=h, json={"title": "x"})
    assert r.status_code == 500
    assert "psycopg2" not in r.text and "10.0.0.5" not in r.text
