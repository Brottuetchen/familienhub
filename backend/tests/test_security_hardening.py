"""Sicherheitsprüfung 18.10.: gehashte Refresh-Tokens, Passwortänderung, PKCE-Bindung des OIDC-Rücksprungs,
CORS und Sicherheits-Header."""

import base64
import hashlib
import importlib.util
import secrets
from pathlib import Path

import sqlalchemy as sa

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.oidc import OIDCExchangeCode
from app.models.user import RefreshToken, User


def _user(client, name, pw="pw-12345-alt"):
    with SessionLocal() as db:
        if not db.query(User).filter(User.username == name).first():
            db.add(User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash(pw), role="partner"))
            db.commit()
    return client.post("/api/auth/login", json={"username": name, "password": pw, "client": "app"}).json()


def test_refresh_tokens_stored_only_as_hash_and_rotate(client):
    login = _user(client, "sec_hash")
    raw = login["refresh_token"]
    with SessionLocal() as db:
        stored = [t.token for t in db.query(RefreshToken).all()]
    assert raw not in stored and hashlib.sha256(raw.encode()).hexdigest() in stored
    r = client.post("/api/auth/refresh", json={"refresh_token": raw})
    assert r.status_code == 200 and r.json()["refresh_token"] != raw
    assert client.post("/api/auth/refresh", json={"refresh_token": raw}).status_code == 401  # rotiert = alt ungültig


def test_password_change_requires_length_and_ends_other_sessions(client):
    a = _user(client, "sec_pw")
    b = client.post("/api/auth/login", json={"username": "sec_pw", "password": "pw-12345-alt", "client": "app"}).json()
    h = {"Authorization": f"Bearer {a['access_token']}"}
    assert client.post("/api/auth/change-password", headers=h,
                       json={"current_password": "pw-12345-alt", "new_password": "kurz"}).status_code == 422
    r = client.post("/api/auth/change-password", headers=h, json={
        "current_password": "pw-12345-alt", "new_password": "neues-langes-pw", "refresh_token": a["refresh_token"]})
    assert r.status_code == 200 and r.json()["other_sessions_ended"] >= 1
    assert client.post("/api/auth/refresh", json={"refresh_token": b["refresh_token"]}).status_code == 401
    assert client.post("/api/auth/refresh", json={"refresh_token": a["refresh_token"]}).status_code == 200


def _challenge(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


def _exchange_code(user_id, challenge):
    code = secrets.token_urlsafe(32)
    with SessionLocal() as db:
        db.add(OIDCExchangeCode(code=code, user_id=user_id, used=False, app_challenge=challenge))
        db.commit()
    return code


def test_oidc_exchange_bound_to_app_secret(client):
    _user(client, "sec_oidc")
    with SessionLocal() as db:
        uid = db.query(User).filter(User.username == "sec_oidc").first().id
    verifier = secrets.token_urlsafe(48)
    # Abgefangener Code ohne Geheimnis nützt nichts – und ist danach verbrannt
    stolen = _exchange_code(uid, _challenge(verifier))
    assert client.post("/api/auth/oidc/exchange", json={"code": stolen}).status_code == 401
    assert client.post("/api/auth/oidc/exchange", json={"code": stolen, "verifier": verifier}).status_code == 401
    wrong = _exchange_code(uid, _challenge(verifier))
    assert client.post("/api/auth/oidc/exchange", json={"code": wrong, "verifier": "falsch"}).status_code == 401
    good = _exchange_code(uid, _challenge(verifier))
    r = client.post("/api/auth/oidc/exchange", json={"code": good, "verifier": verifier})
    assert r.status_code == 200 and r.json()["user"]["username"] == "sec_oidc"


def test_oidc_start_rejects_malformed_challenge(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "oidc_issuer", "https://auth.example/application/o/x/")
    monkeypatch.setattr(settings, "oidc_client_id", "abc")
    assert client.get("/api/auth/oidc/start?client=app&challenge=../../etc").status_code == 400


def test_security_headers_and_no_cors_by_default(client):
    r = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert "access-control-allow-origin" not in r.headers
    assert "access-control-allow-credentials" not in r.headers


def test_migration_hashes_existing_refresh_tokens(tmp_path):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "b3c4d5e6f7a8_security_hardening.py"
    spec = importlib.util.spec_from_file_location("mig_security", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    engine = sa.create_engine(f"sqlite:///{tmp_path}/alt.db")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE refresh_tokens (id INTEGER PRIMARY KEY, token VARCHAR, revoked BOOLEAN)"))
        conn.execute(sa.text("CREATE TABLE oidc_sessions (id INTEGER PRIMARY KEY, state VARCHAR)"))
        conn.execute(sa.text("CREATE TABLE oidc_exchange_codes (id INTEGER PRIMARY KEY, code VARCHAR)"))
        conn.execute(sa.text("INSERT INTO refresh_tokens (token, revoked) VALUES ('klartext-token', 0)"))
        with Operations.context(MigrationContext.configure(conn)):
            mod.upgrade()
            mod.upgrade()  # zweimal: bleibt richtig (keine doppelte Hashung)
        token = conn.execute(sa.text("SELECT token FROM refresh_tokens")).scalar()
        cols = {c["name"] for c in sa.inspect(conn).get_columns("oidc_exchange_codes")}
    assert token == hashlib.sha256(b"klartext-token").hexdigest()
    assert "app_challenge" in cols


def test_oversized_requests_rejected_early(client):
    r = client.post("/api/auth/login", content=b"x" * (2 * 1024 * 1024 + 1), headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert client.post("/api/auth/login", json={"username": "x", "password": "y"}).status_code in (401, 429)
