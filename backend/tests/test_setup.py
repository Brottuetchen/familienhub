"""Ersteinrichtung (#4): Einrichtungscode, erstes Admin-Konto, Verbindungstests, Name/Zeitzone."""

import httpx
import pytest
import respx

from app.config import settings
from app.core.database import SessionLocal
from app.models.user import User
from app.services import setup


@pytest.fixture
def fresh_hub(client):
    """Simuliert einen frischen Hub: vorhandene Admins vorübergehend zu Partnern machen."""
    with SessionLocal() as db:
        admins = db.query(User).filter(User.role == "admin").all()
        ids = [u.id for u in admins]
        for u in admins:
            u.role, u.is_admin = "partner", False
        db.commit()
    yield
    with SessionLocal() as db:
        for u in db.query(User).filter(User.id.in_(ids)).all():
            u.role, u.is_admin = "admin", True
        for u in db.query(User).filter(User.username.like("setup_%")).all():
            db.delete(u)
        db.commit()
    setup.finish()


@pytest.fixture
def no_admin(fresh_hub, monkeypatch):
    """Fresh hub with SETUP_REQUIRE_CODE=true; yields the setup code."""
    monkeypatch.setattr(settings, "setup_require_code", True)
    return setup.new_code()


def _admin(code, name="setup_chef", **kw):
    return {"code": code, "username": name, "email": f"{name}@example.org", "password": "lang-genug-123", **kw}


def test_status_is_public(client):
    r = client.get("/api/setup/status")
    assert r.status_code == 200 and set(r.json()) == {"needs_setup", "version", "app_name", "oidc", "code_required"}


def test_first_admin_needs_code_and_only_once(client, no_admin):
    assert client.get("/api/setup/status").json()["needs_setup"] is True
    assert client.post("/api/setup/admin", json=_admin("AAAA-AAAA")).status_code == 403
    r = client.post("/api/setup/admin", json=_admin(no_admin.lower().replace("-", " "), client="app"))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["is_admin"] is True and body["access_token"] and body["refresh_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["username"] == "setup_chef"
    assert client.get("/api/setup/status").json()["needs_setup"] is False
    # zweites Mal: auch mit dem alten Code nicht mehr
    assert client.post("/api/setup/admin", json=_admin(no_admin, name="setup_zwei")).status_code == 409


def test_too_many_wrong_codes_rotate(client, no_admin):
    for _ in range(setup.MAX_ATTEMPTS):
        assert client.post("/api/setup/admin", json=_admin("ZZZZ-ZZZZ")).status_code == 403
    assert client.post("/api/setup/admin", json=_admin(no_admin)).status_code == 403  # alter Code verbraucht


@pytest.mark.parametrize("override", [{"password": "kurz"}, {"username": "Mit Leerzeichen"}, {"email": "kein-at"}])
def test_first_admin_validation(client, no_admin, override):
    assert client.post("/api/setup/admin", json={**_admin(no_admin), **override}).status_code == 422


def test_status_reports_code_required(client, monkeypatch):
    assert client.get("/api/setup/status").json()["code_required"] is False
    monkeypatch.setattr(settings, "setup_require_code", True)
    assert client.get("/api/setup/status").json()["code_required"] is True


def test_first_admin_without_code_by_default(client, fresh_hub):
    body = _admin("")
    del body["code"]
    assert client.get("/api/setup/status").json()["needs_setup"] is True
    r = client.post("/api/setup/admin", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["user"]["is_admin"] is True
    assert client.get("/api/setup/status").json()["needs_setup"] is False
    # second attempt: setup is closed
    body["username"], body["email"] = "setup_zwei", "setup_zwei@example.org"
    assert client.post("/api/setup/admin", json=body).status_code == 409


def test_code_required_rejects_missing_and_wrong_code(client, no_admin):
    body = _admin("")
    del body["code"]
    assert client.post("/api/setup/admin", json=body).status_code == 403
    assert client.post("/api/setup/admin", json=_admin("AAAA-AAAA")).status_code == 403
    assert client.post("/api/setup/admin", json=_admin(no_admin)).status_code == 201


def test_startup_log_matches_mode(client, fresh_hub, monkeypatch, caplog):
    import logging
    from app.core.database import SessionLocal as S
    caplog.set_level(logging.WARNING, logger="familienhub.setup")
    with S() as db:
        setup.prepare(db)
    assert "first person to open the hub becomes admin" in caplog.text and "setup code" not in caplog.text
    caplog.clear()
    monkeypatch.setattr(settings, "setup_require_code", True)
    with S() as db:
        setup.prepare(db)
    assert "setup code:" in caplog.text


def test_existing_admin_blocks_setup(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "setup_require_code", True)
    setup.new_code()
    assert client.post("/api/setup/admin", json=_admin("ABCD-EFGH")).status_code == 409


# ── Verbindungstests ──────────────────────────────────────────────────────


def test_connection_test_admin_only_and_known_keys(client, auth):
    assert client.post("/api/admin/plugins/seerr/test", json={"values": {}}).status_code == 401
    r = client.post("/api/admin/plugins/seerr/test", headers=auth, json={"values": {"HOMEASSISTANT_TOKEN": "x"}})
    assert r.status_code == 422
    assert client.post("/api/admin/plugins/gibtsnicht/test", headers=auth, json={"values": {}}).status_code == 404


def test_homeassistant_token_checked(client, auth):
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        route = http.get("http://ha.example/api/").mock(side_effect=lambda r: httpx.Response(
            200 if r.headers.get("Authorization") == "Bearer gut" else 401, json={"message": "geheim-intern"}))
        good = client.post("/api/admin/plugins/homeassistant/test", headers=auth,
                           json={"values": {"HOMEASSISTANT_URL": "http://ha.example", "HOMEASSISTANT_TOKEN": "gut"}}).json()
        bad = client.post("/api/admin/plugins/homeassistant/test", headers=auth,
                          json={"values": {"HOMEASSISTANT_URL": "http://ha.example", "HOMEASSISTANT_TOKEN": "falsch"}}).json()
    assert good == {"ok": True, "level": "ok", "message": "Home Assistant: verbunden, Token gültig"}
    assert bad["ok"] is False and "Token ungültig" in bad["message"]
    assert route.call_count == 2 and "geheim" not in str(good) + str(bad) and "falsch" not in bad["message"]


def test_blank_secret_uses_saved_value(client, auth, monkeypatch):
    monkeypatch.setenv("SEERR_API_KEY", "gespeichert")
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        http.get("http://seerr.example/api/v1/settings/main").mock(
            side_effect=lambda r: httpx.Response(200 if r.headers.get("X-Api-Key") == "gespeichert" else 403))
        r = client.post("/api/admin/plugins/seerr/test", headers=auth,
                        json={"values": {"SEERR_URL": "http://seerr.example", "SEERR_API_KEY": ""}}).json()
    assert r["ok"] is True


def test_unreachable_and_invalid_addresses(client, auth):
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        http.get("http://paperless.example/api/").mock(side_effect=httpx.ConnectError("intern"))
        r = client.post("/api/admin/plugins/paperless/test", headers=auth,
                        json={"values": {"PAPERLESS_URL": "http://paperless.example"}}).json()
    assert r == {"ok": False, "level": "error", "message": "Nicht erreichbar – Adresse prüfen (vom Server aus erreichbar?)"}
    w = client.post("/api/admin/plugins/weather/test", headers=auth,
                    json={"values": {"WEATHER_LATITUDE": "abc", "WEATHER_LONGITUDE": "1"}}).json()
    assert w["ok"] is False and "Zahl" in w["message"]


def test_nextcloud_without_shared_calendar_is_info(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "caldav_url", None, raising=False)
    r = client.post("/api/admin/plugins/nextcloud/test", headers=auth, json={"values": {"CALDAV_URL": ""}}).json()
    assert r["ok"] is True and r["level"] == "info"


# ── Name und Zeitzone ─────────────────────────────────────────────────────


def test_core_settings(client, auth):
    old = client.get("/api/admin/core", headers=auth).json()
    try:
        r = client.put("/api/admin/core", headers=auth, json={"app_name": "Familie Beispiel", "timezone": "Europe/Vienna"})
        assert r.json() == {"app_name": "Familie Beispiel", "timezone": "Europe/Vienna"}
        assert client.get("/api/setup/status").json()["app_name"] == "Familie Beispiel"
        assert client.put("/api/admin/core", headers=auth, json={"app_name": "X", "timezone": "Mond/Krater"}).status_code == 422
    finally:
        client.put("/api/admin/core", headers=auth, json=old)
