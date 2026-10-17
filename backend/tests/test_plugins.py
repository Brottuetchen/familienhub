"""Plugin-Schnittstelle (Issue #18): Laden, Fähigkeiten, Abschalten, Einstellungen."""

from types import SimpleNamespace

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.plugins import Plugin, Setting, get_setting
from app.plugins import registry as registry_module
from app.plugins.registry import PluginRegistry


def test_modules_follow_plugin_configuration(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "homeassistant_url", None)
    monkeypatch.setattr(settings, "shelfarr_url", None)
    m = client.get("/api/modules", headers=auth).json()["modules"]
    assert m["today"] == {"enabled": True, "core": True, "plugin": None}
    assert m["tasks"]["enabled"] is True and m["tasks"]["plugin"] == "nextcloud"
    assert m["shopping"]["enabled"] is False
    assert m["books"]["enabled"] is False

    monkeypatch.setattr(settings, "homeassistant_url", "http://ha.test")
    monkeypatch.setattr(settings, "homeassistant_token", "t")
    m = client.get("/api/modules", headers=auth).json()["modules"]
    assert m["shopping"] == {"enabled": True, "core": False, "plugin": "homeassistant"}
    assert m["meal_source"]["plugin"] == "homeassistant"


def test_plugins_disabled_switches_module_and_connector_off(client, auth, monkeypatch):
    from app.connectors.registry import registry

    monkeypatch.setattr(settings, "homeassistant_url", "http://ha.test")
    monkeypatch.setattr(settings, "homeassistant_token", "t")
    monkeypatch.setattr(settings, "plugins_disabled", "homeassistant, weather")
    body = client.get("/api/modules", headers=auth).json()
    assert body["modules"]["shopping"]["enabled"] is False
    ha = next(p for p in body["plugins"] if p["id"] == "homeassistant")
    assert ha["configured"] is True and ha["disabled"] is True and ha["active"] is False
    assert registry.get("homeassistant") is None
    assert client.get("/api/shopping", headers=auth).json()["status"] == "not_configured"


def _fake_entry_points(*items):
    def entry_points(group=None):
        assert group == "familienhub.plugins"
        return [SimpleNamespace(name=n, load=loader) for n, loader in items]
    return entry_points


def test_external_plugin_loaded_with_router_and_settings(monkeypatch):
    router = APIRouter(prefix="/api/grocy")

    @router.get("/ping")
    async def ping():
        return {"pong": True}

    class GrocyPlugin(Plugin):
        def __init__(self):
            super().__init__(id="grocy", name="Grocy", capabilities=frozenset({"shopping"}),
                             settings=(Setting("GROCY_URL", "Adresse"),))

        def routers(self):
            return [router]

    def broken():
        raise ImportError("kaputt")

    monkeypatch.setattr(registry_module, "entry_points", _fake_entry_points(
        ("grocy", lambda: GrocyPlugin), ("kaputt", broken), ("doppelt", lambda: GrocyPlugin),
        ("kein_plugin", lambda: object),
    ))
    reg = PluginRegistry()
    reg.load()
    ids = [p.id for p in reg.all()]
    assert ids.count("grocy") == 1  # doppelte ID übersprungen, kaputtes Plugin ignoriert
    assert {"nextcloud", "homeassistant", "shelfarr", "weather"} <= set(ids)

    grocy = reg.get("grocy")
    monkeypatch.delenv("GROCY_URL", raising=False)
    assert grocy.is_configured() is False and grocy.missing_settings() == ["GROCY_URL"]
    monkeypatch.setenv("GROCY_URL", "http://grocy.test")
    assert grocy.is_configured() is True

    app = FastAPI()
    reg.include_routers(app)
    assert TestClient(app).get("/api/grocy/ping").json() == {"pong": True}


def test_builtin_wins_capability_over_external(monkeypatch):
    class OtherShopping(Plugin):
        def __init__(self):
            super().__init__(id="other", name="Other", capabilities=frozenset({"shopping"}))

        def is_configured(self):
            return True

    monkeypatch.setattr(registry_module, "entry_points", _fake_entry_points(("other", lambda: OtherShopping)))
    monkeypatch.setattr(settings, "homeassistant_url", "http://ha.test")
    monkeypatch.setattr(settings, "homeassistant_token", "t")
    reg = PluginRegistry()
    reg.load()
    assert reg.provider("shopping").id == "homeassistant"
    monkeypatch.setattr(settings, "plugins_disabled", "homeassistant")
    assert reg.provider("shopping").id == "other"


def test_get_setting_precedence(monkeypatch):
    from app.services import config_store

    monkeypatch.setenv("MEIN_PLUGIN_KEY", "aus-env")
    assert get_setting("MEIN_PLUGIN_KEY") == "aus-env"
    monkeypatch.setitem(config_store._extra, "MEIN_PLUGIN_KEY", "aus-admin")
    assert get_setting("MEIN_PLUGIN_KEY") == "aus-admin"
    monkeypatch.setattr(settings, "shelfarr_language", "en")
    assert get_setting("SHELFARR_LANGUAGE") == "en"
