"""Plugin status after saving (#60): weather is set up once coordinates are saved; overview and ntfy check."""

import httpx
import pytest
import respx

from app.config import settings
from app.core.database import SessionLocal
from app.models.config import ConfigOverride
from app.services import config_store


@pytest.fixture
def weather_off(monkeypatch):
    for attr in ("weather_enabled", "weather_latitude", "weather_longitude", "weather_location_name"):
        monkeypatch.setattr(settings, attr, getattr(settings, attr))
    monkeypatch.setattr(settings, "weather_enabled", False)
    monkeypatch.setattr(settings, "plugins_disabled", "")
    yield
    keys = ("WEATHER_LATITUDE", "WEATHER_LONGITUDE", "WEATHER_LOCATION_NAME")
    with SessionLocal() as db:
        for k in keys:
            row = db.get(ConfigOverride, k)
            if row:
                db.delete(row)
        db.commit()
    for k in keys:
        config_store._saved.discard(k)


def _weather(client, auth):
    return next(p for p in client.get("/api/admin/overview", headers=auth).json()["plugins"] if p["id"] == "weather")


def test_weather_becomes_set_up_when_coordinates_are_saved(client, auth, weather_off):
    before = _weather(client, auth)
    assert before["configured"] is False and before["active"] is False
    assert before["health"]["status"] == "off"

    r = client.put("/api/admin/settings", headers=auth, json={"values": {
        "WEATHER_LATITUDE": "48.14", "WEATHER_LONGITUDE": "11.58", "WEATHER_LOCATION_NAME": "München"}})
    assert r.status_code == 200
    after = _weather(client, auth)
    assert after["configured"] is True and after["active"] is True
    assert after["health"]["status"] == "ok" and "München" in after["health"]["message"]
    view = next(p for p in client.get("/api/admin/settings", headers=auth).json() if p["id"] == "weather")
    assert view["configured"] is True and view["active"] is True
    assert client.get("/api/modules", headers=auth).json()["modules"]["weather"]["enabled"] is True


def test_weather_default_location_counts_as_set_up(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "weather_enabled", True)
    monkeypatch.setattr(settings, "plugins_disabled", "")
    assert _weather(client, auth)["configured"] is True


def test_ntfy_connection_check(client, auth):
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        http.get("http://ntfy.example/v1/health").mock(side_effect=lambda r: httpx.Response(
            200 if r.headers.get("Authorization") == "Bearer gut" else 401, json={"healthy": True}))
        good = client.post("/api/admin/plugins/ntfy/test", headers=auth,
                           json={"values": {"NTFY_URL": "http://ntfy.example", "NTFY_TOKEN": "gut"}}).json()
        bad = client.post("/api/admin/plugins/ntfy/test", headers=auth,
                          json={"values": {"NTFY_URL": "http://ntfy.example", "NTFY_TOKEN": "falsch"}}).json()
    assert good["ok"] is True and bad["ok"] is False and "Token ungültig" in bad["message"]
