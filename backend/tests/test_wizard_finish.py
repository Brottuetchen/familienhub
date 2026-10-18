"""End of the setup wizard: unused active plugins are switched off, chosen and set-up ones stay."""

import pytest

from app.config import settings
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.config import ConfigOverride
from app.models.user import User


@pytest.fixture
def clean_overrides(monkeypatch):
    monkeypatch.setattr(settings, "plugins_disabled", "")
    monkeypatch.setattr(settings, "weather_enabled", True)
    yield
    with SessionLocal() as db:
        for key in ("PLUGINS_DISABLED", "TASKS_SOURCES", "CALENDAR_SOURCES", "SHOPPING_SOURCE"):
            row = db.get(ConfigOverride, key)
            if row:
                db.delete(row)
        db.commit()


def _plugins(client, auth):
    return {p["id"]: p for p in client.get("/api/admin/settings", headers=auth).json()}


def test_finish_disables_unused_and_keeps_chosen(client, auth, monkeypatch, clean_overrides):
    monkeypatch.setenv("NTFY_URL", "http://ntfy.test")
    monkeypatch.setenv("PAPERLESS_URL", "http://paperless.test")
    before = _plugins(client, auth)
    assert {k: before[k]["active"] for k in ("ntfy", "paperless", "nextcloud")} == dict.fromkeys(("ntfy", "paperless", "nextcloud"), True)

    # What the wizard saved before: tasks only from the hub, calendar from the hub plus the ICS feeds
    assert client.put("/api/admin/sources", headers=auth, json={"area": "tasks", "selected": ["hub_tasks"]}).status_code == 200
    assert client.put("/api/admin/sources", headers=auth, json={"area": "calendar", "selected": ["hub_calendar", "ics"]}).status_code == 200
    # ICS is not set up (no feed), so it is not active; paperless was configured in the services step
    r = client.post("/api/admin/setup/finish", headers=auth, json={"keep": ["paperless"]})
    assert r.status_code == 200
    disabled = set(r.json()["disabled"])
    assert {"ntfy", "nextcloud"} <= disabled, disabled
    assert not disabled & {"paperless", "weather", "hub_tasks", "hub_shopping", "hub_calendar"}

    after = _plugins(client, auth)
    assert after["ntfy"]["disabled"] and not after["ntfy"]["active"]
    assert after["paperless"]["active"] and after["weather"]["active"]
    mods = client.get("/api/modules", headers=auth).json()["modules"]
    assert mods["weather"]["enabled"] is True

    # Reversible per plugin
    assert client.put("/api/admin/plugins/ntfy", headers=auth, json={"enabled": True}).json()["active"] is True


def test_finish_keeps_plugins_that_serve_an_area(client, auth, clean_overrides):
    assert client.put("/api/admin/sources", headers=auth, json={"area": "tasks", "selected": ["hub_tasks", "nextcloud"]}).status_code == 200
    disabled = client.post("/api/admin/setup/finish", headers=auth, json={"keep": []}).json()["disabled"]
    assert "nextcloud" not in disabled and "hub_tasks" not in disabled


def test_finish_is_idempotent_and_leaves_unconfigured_alone(client, auth, clean_overrides):
    first = client.post("/api/admin/setup/finish", headers=auth, json={"keep": []}).json()["disabled"]
    assert "seerr" not in first  # not set up: nothing to switch off
    assert client.post("/api/admin/setup/finish", headers=auth, json={"keep": []}).json()["disabled"] == []


def test_finish_requires_admin(client):
    with SessionLocal() as db:
        if not db.query(User).filter(User.username == "wz_partner").first():
            db.add(User(username="wz_partner", email="wz@test.de", hashed_password=get_password_hash("pw-12345"), role="partner"))
            db.commit()
    tok = client.post("/api/auth/login", json={"username": "wz_partner", "password": "pw-12345"}).json()["access_token"]
    assert client.post("/api/admin/setup/finish", headers={"Authorization": f"Bearer {tok}"}, json={"keep": []}).status_code == 403
