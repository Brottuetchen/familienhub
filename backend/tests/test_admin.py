"""Admin: Plugin-Einstellungen im UI (Laufzeit-Config, Secrets maskiert und verschlüsselt)."""

import pytest

from app.config import settings
from app.core.database import SessionLocal
from app.models.config import ConfigOverride


@pytest.fixture
def clean_overrides():
    before = (settings.shelfarr_url, settings.shelfarr_token)
    yield
    with SessionLocal() as db:
        db.query(ConfigOverride).delete()
        db.commit()
    settings.shelfarr_url, settings.shelfarr_token = before


def test_admin_settings_lists_plugins_with_fields(client, auth):
    data = client.get("/api/admin/settings", headers=auth).json()
    by_id = {p["id"]: p for p in data}
    assert {"nextcloud", "homeassistant", "shelfarr", "weather"} <= set(by_id)
    keys = {f["key"] for f in by_id["homeassistant"]["fields"]}
    assert {"HOMEASSISTANT_URL", "HOMEASSISTANT_TOKEN"} <= keys
    token = next(f for f in by_id["homeassistant"]["fields"] if f["key"] == "HOMEASSISTANT_TOKEN")
    assert token["secret"] is True


def test_admin_settings_forbidden_for_child(client, auth):
    client.post("/api/auth/users", headers=auth,
                json={"username": "kidcfg", "email": "kc@t.de", "password": "kids1234", "role": "child"})
    tok = client.post("/api/auth/login", json={"username": "kidcfg", "password": "kids1234"}).json()["access_token"]
    assert client.get("/api/admin/settings", headers={"Authorization": f"Bearer {tok}"}).status_code == 403


def test_admin_update_applies_live_and_masks_secret(client, auth, clean_overrides):
    r = client.put("/api/admin/settings", headers=auth,
                   json={"values": {"SHELFARR_URL": "http://shelf:5056", "SHELFARR_TOKEN": "tok-secret", "UNBEKANNT": "x"}})
    assert r.status_code == 200
    # sofort wirksam, ohne Neustart
    assert settings.shelfarr_url == "http://shelf:5056"
    assert settings.shelfarr_token == "tok-secret"
    shelf = next(p for p in client.get("/api/admin/settings", headers=auth).json() if p["id"] == "shelfarr")
    url_f = next(f for f in shelf["fields"] if f["key"] == "SHELFARR_URL")
    tok_f = next(f for f in shelf["fields"] if f["key"] == "SHELFARR_TOKEN")
    assert url_f["value"] == "http://shelf:5056"
    assert tok_f["value"] == "" and tok_f["is_set"] is True
    assert shelf["active"] is True
    # leeres Secret bleibt erhalten
    client.put("/api/admin/settings", headers=auth, json={"values": {"SHELFARR_TOKEN": ""}})
    assert settings.shelfarr_token == "tok-secret"
    with SessionLocal() as db:
        row = db.get(ConfigOverride, "SHELFARR_TOKEN")
        assert row is not None and row.secret is True and "tok-secret" not in row.value
        assert db.get(ConfigOverride, "UNBEKANNT") is None
