"""Verwaltung: Übersicht, Familie & Verbindungen, Haus-Auswahl, Protokoll – nur für Admins."""

import logging

import httpx
import pytest
import respx

from app.config import settings
from app.core import log_buffer
from app.core.crypto import encrypt
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.paperless import PaperlessAccount
from app.models.user import User
from app.routers import admin_panel


def _user(client, name, role="partner"):
    with SessionLocal() as db:
        u = db.query(User).filter(User.username == name).first()
        if not u:
            u = User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"),
                     role=role, is_admin=role == "admin")
            db.add(u)
            db.commit()
        uid = u.id
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return uid, {"Authorization": f"Bearer {tok}"}


@pytest.mark.parametrize("path", ["/api/admin/overview", "/api/admin/users", "/api/admin/house/entities", "/api/admin/log"])
def test_only_admins(client, path):
    _, h = _user(client, "vw_partner")
    assert client.get(path, headers=h).status_code == 403
    assert client.get(path).status_code == 401


def test_overview_checks_reachability_without_leaking_urls(client, auth, monkeypatch):
    monkeypatch.setenv("PAPERLESS_URL", "http://paperless.intern:8000")
    monkeypatch.setenv("SEERR_URL", "http://seerr.intern:5055")
    monkeypatch.setenv("SEERR_API_KEY", "k")
    admin_panel._health_cache.clear()
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        paperless = http.get("http://paperless.intern:8000").respond(302)
        http.get("http://seerr.intern:5055").mock(side_effect=httpx.ConnectError("seerr.intern refused"))
        data = client.get("/api/admin/overview", headers=auth).json()
        again = client.get("/api/admin/overview", headers=auth).json()
    plugins = {p["id"]: p for p in data["plugins"]}
    assert plugins["paperless"]["health"]["status"] == "ok"
    assert plugins["seerr"]["health"] == {"status": "error", "message": "Nicht erreichbar"}
    assert "intern" not in str(data)
    assert paperless.call_count == 1 and again["plugins"] == data["plugins"]  # 30 s gemerkt
    assert data["server"]["version"] and data["users"]["active"] >= 1
    assert set(data["push"]) == {"fcm", "webpush", "devices"}


def test_inactive_plugin_is_not_contacted(client, auth, monkeypatch):
    monkeypatch.delenv("SEERR_URL", raising=False)
    data = client.get("/api/admin/overview", headers=auth).json()
    seerr = next(p for p in data["plugins"] if p["id"] == "seerr")
    assert seerr["health"]["status"] == "off" and "SEERR_URL" in seerr["missing"]


def test_users_show_links_but_no_secrets(client, auth, monkeypatch):
    monkeypatch.setenv("PAPERLESS_URL", "http://paperless.test")
    uid, _ = _user(client, "vw_anna")
    with SessionLocal() as db:
        if not db.get(PaperlessAccount, uid):
            db.add(PaperlessAccount(user_id=uid, token_enc=encrypt("geheimes-token"), remote_username="anna"))
            db.commit()
    data = client.get("/api/admin/users", headers=auth).json()
    anna = next(u for u in data if u["username"] == "vw_anna")
    assert anna["role"] == "partner" and anna["is_active"] is True
    assert anna["links"]["paperless"] is True
    assert "geheimes" not in str(data) and "hashed_password" not in str(data)


def test_admin_cannot_lock_themselves_out(client, auth):
    me = client.get("/api/auth/me", headers=auth).json()["id"]
    assert client.patch(f"/api/auth/users/{me}", headers=auth, json={"is_active": False}).status_code == 400
    assert client.patch(f"/api/auth/users/{me}", headers=auth, json={"role": "partner"}).status_code == 400
    uid, _ = _user(client, "vw_kind")
    r = client.patch(f"/api/auth/users/{uid}", headers=auth, json={"role": "child", "is_active": False})
    assert r.status_code == 200 and r.json()["role"] == "child" and r.json()["is_active"] is False


def test_house_entities_for_picker(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "homeassistant_url", "http://ha.test")
    monkeypatch.setattr(settings, "homeassistant_token", "t")
    monkeypatch.setattr(settings, "ha_house_entities", "sensor.temp,light.lamp")
    monkeypatch.setattr(settings, "ha_house_write_entities", "light.lamp")
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        http.get("http://ha.test/api/states").respond(200, json=[
            {"entity_id": "light.lamp", "state": "on", "attributes": {"friendly_name": "Lampe", "token": "x"}},
            {"entity_id": "sensor.temp", "state": "21.5", "attributes": {"friendly_name": "Wohnzimmer", "unit_of_measurement": "°C"}},
            {"entity_id": "automation.secret", "state": "on", "attributes": {}},
            {"entity_id": "update.core", "state": "off", "attributes": {}},
        ])
        data = client.get("/api/admin/house/entities", headers=auth).json()
    assert data["status"] == "ok"
    assert [(i["entity_id"], i["controllable"]) for i in data["items"]] == [("light.lamp", True), ("sensor.temp", False)]
    assert data["items"][1]["unit"] == "°C" and "token" not in str(data["items"])
    assert data["selection"] == {"display": ["sensor.temp", "light.lamp"], "control": ["light.lamp"], "max": 6}


def test_log_buffer_redacts_secrets(client, auth):
    log_buffer.clear()
    logging.getLogger("hermes.test").warning("Aufruf fehlgeschlagen token=abc123 Bearer xyz fhp_" + "a" * 20)
    logging.getLogger("hermes.test").info("nur Info")
    items = client.get("/api/admin/log", headers=auth).json()["items"]
    assert len(items) == 1 and items[0]["level"] == "WARNING" and items[0]["source"] == "hermes.test"
    assert "abc123" not in items[0]["message"] and "xyz" not in items[0]["message"] and "aaaa" not in items[0]["message"]
