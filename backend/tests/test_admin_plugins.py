"""Admin: Plugins in der App an- und abschalten (statt PLUGINS_DISABLED in der .env)."""

from app.config import settings
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.config import ConfigOverride
from app.models.user import User


def _partner(client):
    with SessionLocal() as db:
        if not db.query(User).filter(User.username == "pl_partner").first():
            db.add(User(username="pl_partner", email="pl@test.de", hashed_password=get_password_hash("pw-12345"), role="partner"))
            db.commit()
    tok = client.post("/api/auth/login", json={"username": "pl_partner", "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_toggle_plugin_persists_and_hides_module(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "weather_enabled", True)
    monkeypatch.setattr(settings, "plugins_disabled", "")
    assert client.get("/api/modules", headers=auth).json()["modules"]["weather"]["enabled"] is True

    r = client.put("/api/admin/plugins/weather", headers=auth, json={"enabled": False})
    assert r.status_code == 200 and r.json()["disabled"] is True and r.json()["active"] is False
    assert client.get("/api/modules", headers=auth).json()["modules"]["weather"]["enabled"] is False
    with SessionLocal() as db:
        assert db.get(ConfigOverride, "PLUGINS_DISABLED").value == "weather"

    r = client.put("/api/admin/plugins/weather", headers=auth, json={"enabled": True})
    assert r.json()["disabled"] is False
    assert client.get("/api/modules", headers=auth).json()["modules"]["weather"]["enabled"] is True
    with SessionLocal() as db:
        assert db.get(ConfigOverride, "PLUGINS_DISABLED").value == ""


def test_toggle_requires_admin_and_known_plugin(client, auth):
    assert client.put("/api/admin/plugins/weather", headers=_partner(client), json={"enabled": False}).status_code == 403
    assert client.put("/api/admin/plugins/gibtsnicht", headers=auth, json={"enabled": False}).status_code == 404


def test_settings_view_shows_disabled_state(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "plugins_disabled", "shelfarr")
    plugins = {p["id"]: p for p in client.get("/api/admin/settings", headers=auth).json()}
    assert plugins["shelfarr"]["disabled"] is True and plugins["nextcloud"]["disabled"] is False
