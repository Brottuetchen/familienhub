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


def test_full_access_key_reaches_normal_api_but_voice_key_does_not(client):
    a = _auth(client, "tok_full")
    full = client.post("/api/auth/api-tokens", headers=a, json={"name": "Full"}).json()
    voice = client.post("/api/auth/api-tokens", headers=a, json={"name": "Voice", "scopes": ["voice"]}).json()
    assert full["scopes"] is None and voice["scopes"]

    full_h = {"Authorization": f"Bearer {full['token']}"}
    voice_h = {"Authorization": f"Bearer {voice['token']}"}
    assert client.get("/api/tasks", headers=full_h).status_code == 200
    assert client.get("/api/today", headers=full_h).status_code == 200
    assert client.get("/api/tasks", headers=voice_h).status_code == 403
    assert client.get("/api/today", headers=voice_h).status_code == 403

    listed = {t["name"]: t["scopes"] for t in client.get("/api/auth/api-tokens", headers=a).json()}
    assert listed["Full"] is None and listed["Voice"] == voice["scopes"]


def _key_with(client, name, scopes):
    a = _auth(client, name)
    r = client.post("/api/auth/api-tokens", headers=a, json={"name": "K", "scopes": scopes})
    assert r.status_code == 201, r.text
    return a, r.json(), {"Authorization": f"Bearer {r.json()['token']}"}


def test_fine_grained_scope_matrix(client):
    _, created, k = _key_with(client, "tok_fine", ["api:tasks:read", "api:shopping:write"])
    # write implies read
    assert set(created["scopes"]) == {"api:tasks:read", "api:shopping:write", "api:shopping:read"}
    assert client.get("/api/tasks", headers=k).status_code == 200
    assert client.get("/api/shopping", headers=k).status_code != 403
    # other area, write route of a read-only area, untagged route
    assert client.get("/api/today", headers=k).status_code == 403
    assert client.post("/api/tasks", headers=k, json={"summary": "x"}).status_code == 403
    assert client.get("/api/calendar/events", headers=k).status_code == 403
    assert client.get("/api/auth/me", headers=k).status_code == 403
    assert client.get("/api/admin/settings", headers=k).status_code == 403


def test_scoped_key_cannot_manage_keys(client):
    _, _, k = _key_with(client, "tok_mint", ["read"])
    assert client.get("/api/auth/api-tokens", headers=k).status_code == 403
    assert client.post("/api/auth/api-tokens", headers=k, json={"name": "evil"}).status_code == 403
    assert client.delete("/api/auth/api-tokens/1", headers=k).status_code == 403


def test_read_preset_reads_everywhere_but_writes_nowhere(client):
    _, created, k = _key_with(client, "tok_read", ["read"])
    assert created["scopes"] and all(s.startswith("api:") and s.endswith(":read") for s in created["scopes"])
    for path in ("/api/today", "/api/tasks", "/api/shopping", "/api/meals", "/api/reminders"):
        assert client.get(path, headers=k).status_code == 200, path
    assert client.post("/api/tasks", headers=k, json={"summary": "x"}).status_code == 403
    assert client.post("/api/shopping", headers=k, json={"summary": "x"}).status_code == 403
    assert client.post("/api/reminders", headers=k, json={}).status_code == 403


def test_voice_keys_do_not_reach_normal_api_and_unknown_scope_rejected(client):
    _, _, v = _key_with(client, "tok_voice2", ["voice"])
    assert client.get("/api/voice/shopping", headers=v).status_code == 200
    assert client.get("/api/shopping", headers=v).status_code == 403  # voice scope names != api scopes
    assert client.get("/api/tasks", headers=v).status_code == 403
    a = _auth(client, "tok_bad")
    assert client.post("/api/auth/api-tokens", headers=a, json={"name": "K", "scopes": ["api:nope:read"]}).status_code == 400
    assert client.post("/api/auth/api-tokens", headers=a, json={"name": "K", "scopes": ["admin"]}).status_code == 400


def test_unrestricted_key_still_reaches_everything_a_session_does(client):
    a = _auth(client, "tok_null")
    raw = client.post("/api/auth/api-tokens", headers=a, json={"name": "K"}).json()["token"]
    h = {"Authorization": f"Bearer {raw}"}
    assert client.get("/api/auth/me", headers=h).status_code == 200
    assert client.get("/api/tasks", headers=h).status_code == 200
