"""Einladungen: Person anlegen, Code einlösen (eigenes Passwort), erneuern, zurückziehen."""

from datetime import datetime, timedelta

import pytest

from app.core.database import SessionLocal
from app.models.invite import Invite
from app.models.user import User


def _invite(client, auth, email, name="Oma", role="guest"):
    return client.post("/api/admin/invites", headers=auth, json={"display_name": name, "email": email, "role": role})


def test_invite_creates_person_and_code(client, auth):
    r = _invite(client, auth, "oma.inv1@example.org")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["display_name"] == "Oma" and body["role"] == "guest" and body["username"].startswith("oma.inv1")
    assert len(body["code"]) == 14 and body["code"].count("-") == 2
    with SessionLocal() as db:
        inv = db.get(Invite, body["id"])
        assert inv.code_hash != body["code"] and inv.code_hash == Invite.hash(body["code"])  # nur Hash gespeichert
    listed = client.get("/api/admin/invites", headers=auth).json()["items"]
    assert any(i["id"] == body["id"] for i in listed) and all("code" not in i for i in listed)


def test_only_admins_and_unique_email(client, auth):
    assert client.post("/api/admin/invites", json={"display_name": "X", "email": "x@example.org"}).status_code == 401
    assert _invite(client, auth, "dup.inv@example.org").status_code == 201
    assert _invite(client, auth, "DUP.inv@example.org").status_code == 409
    assert _invite(client, auth, "kein-at").status_code == 422
    assert _invite(client, auth, "rolle.inv@example.org", role="superuser").status_code == 422


def test_accept_sets_password_and_logs_in_once(client, auth):
    body = _invite(client, auth, "ben.inv2@example.org", name="Ben", role="partner").json()
    r = client.post("/api/invites/accept", json={"code": body["code"].lower().replace("-", " "), "password": "mein-eigenes-pw", "client": "app"})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["username"] == body["username"] and r.json()["refresh_token"]
    login = client.post("/api/auth/login", json={"username": body["username"], "password": "mein-eigenes-pw"})
    assert login.status_code == 200
    again = client.post("/api/invites/accept", json={"code": body["code"], "password": "anderes-passwort"})
    assert again.status_code == 403  # nur einmal
    assert all(i["id"] != body["id"] for i in client.get("/api/admin/invites", headers=auth).json()["items"])


def test_expired_and_short_password(client, auth):
    body = _invite(client, auth, "alt.inv3@example.org").json()
    assert client.post("/api/invites/accept", json={"code": body["code"], "password": "kurz"}).status_code == 422
    with SessionLocal() as db:
        db.get(Invite, body["id"]).expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.commit()
    assert client.post("/api/invites/accept", json={"code": body["code"], "password": "lang-genug-123"}).status_code == 403


def test_renew_invalidates_old_code(client, auth):
    first = _invite(client, auth, "neu.inv4@example.org").json()
    second = client.post(f"/api/admin/invites/{first['id']}/renew", headers=auth).json()
    assert second["code"] != first["code"]
    assert client.post("/api/invites/accept", json={"code": first["code"], "password": "lang-genug-123"}).status_code == 403
    assert client.post("/api/invites/accept", json={"code": second["code"], "password": "lang-genug-123"}).status_code == 200


def test_revoke_deactivates_unused_account(client, auth):
    body = _invite(client, auth, "weg.inv5@example.org").json()
    r = client.delete(f"/api/admin/invites/{body['id']}", headers=auth)
    assert r.json() == {"revoked": True, "deactivated": True}
    with SessionLocal() as db:
        assert db.get(User, body["user_id"]).is_active is False
    assert client.post("/api/invites/accept", json={"code": body["code"], "password": "lang-genug-123"}).status_code == 403


def test_wrong_codes_are_rate_limited(client):
    codes = [client.post("/api/invites/accept", json={"code": "AAAA-AAAA-AAAA", "password": "lang-genug-123"}).status_code
             for _ in range(7)]
    assert codes[:5] == [403] * 5 and 429 in codes[5:]


@pytest.fixture(autouse=True)
def _clear_attempts():
    from app.models.user import LoginAttempt
    with SessionLocal() as db:
        db.query(LoginAttempt).filter(LoginAttempt.username == "einladung").delete()
        db.commit()
    yield
