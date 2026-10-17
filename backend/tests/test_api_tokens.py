"""Persönliche Zugangsschlüssel (z. B. für Sprachassistenten)."""

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.api_token import ApiToken
from app.models.user import User


def _auth(client, name: str) -> dict:
    with SessionLocal() as db:
        if not db.query(User).filter(User.username == name).first():
            db.add(User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"), role="partner"))
            db.commit()
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_create_use_and_revoke_token(client):
    a = _auth(client, "tok_a")
    created = client.post("/api/auth/api-tokens", headers=a, json={"name": "Sprachassistent"})
    assert created.status_code == 201
    raw = created.json()["token"]
    assert raw.startswith("fhp_")

    # Mit dem Schlüssel handelt man als genau diese Person
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {raw}"})
    assert me.status_code == 200 and me.json()["username"] == "tok_a"

    listed = client.get("/api/auth/api-tokens", headers=a).json()
    assert [t["name"] for t in listed] == ["Sprachassistent"]
    assert "token" not in listed[0]
    assert listed[0]["last_used_at"] is not None

    # Nur der Hash liegt in der Datenbank
    with SessionLocal() as db:
        row = db.query(ApiToken).filter(ApiToken.id == created.json()["id"]).one()
        assert row.token_hash != raw and raw not in row.token_hash

    assert client.delete(f"/api/auth/api-tokens/{created.json()['id']}", headers=a).status_code == 204
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {raw}"}).status_code == 401
    assert client.get("/api/auth/api-tokens", headers=a).json() == []


def test_cannot_revoke_foreign_token(client):
    a, b = _auth(client, "tok_b"), _auth(client, "tok_c")
    tid = client.post("/api/auth/api-tokens", headers=a, json={"name": "Sprachassistent"}).json()["id"]
    assert client.delete(f"/api/auth/api-tokens/{tid}", headers=b).status_code == 404
    assert [t["id"] for t in client.get("/api/auth/api-tokens", headers=a).json()] == [tid]


def test_unknown_or_malformed_token_rejected(client):
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer fhp_falsch"}).status_code == 401


def test_token_of_disabled_user_rejected(client):
    a = _auth(client, "tok_d")
    raw = client.post("/api/auth/api-tokens", headers=a, json={"name": "Sprachassistent"}).json()["token"]
    with SessionLocal() as db:
        db.query(User).filter(User.username == "tok_d").update({"is_active": False})
        db.commit()
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {raw}"}).status_code == 401
