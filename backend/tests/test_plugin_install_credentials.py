"""Credentials at install time: the install flow asks for required settings and secrets, stores secrets encrypted,
runs the plugin's own connection test with the values just entered, and a plugin that still lacks a required
setting is "needs setup" and runs none of its hooks (docs/plugins.md)."""

import asyncio

from app.core.crypto import decrypt
from app.core.database import SessionLocal
from app.models.config import ConfigOverride
from app.plugins import jobs
from app.plugins.registry import plugin_registry
from tests.test_plugin_installer import (SHA1, TOKEN, gh, install, inspect, manifest_dict,  # noqa: F401
                                         plugin_code, repo_files)

HOOKS = '''
    schedule_minutes = 5
    runs = 0

    async def test_settings(self, values):
        if not values.get("DEMO_HUB_TOKEN"):
            return {"ok": False, "level": "error", "message": "Token missing"}
        if values["DEMO_HUB_TOKEN"] != "tok-secret-123":
            return {"ok": False, "level": "error", "message": "Token rejected by " + values["DEMO_HUB_URL"]}
        return {"ok": True, "level": "ok", "message": "Connected, token valid"}

    async def today_cards(self, user, db):
        return [{"id": "s", "title": "Demo", "image": "/api/plugins/demo_hub/items", "lines": [{"text": "hi"}]}]

    async def scheduled(self, db):
        type(self).runs += 1
'''


def publish_with_hooks(gh, required_token=False):
    manifest = manifest_dict()
    if required_token:
        manifest["settings"][1]["required"] = True
    gh.publish(SHA1, repo_files(manifest=manifest, code=plugin_code() + HOOKS))


def test_inspect_asks_for_the_secret_and_marks_required(client, auth, gh):
    publish_with_hooks(gh, required_token=True)
    form = {f["key"]: f for f in inspect(client, auth).json()["settings"]}
    assert form["DEMO_HUB_TOKEN"]["secret"] is True and form["DEMO_HUB_TOKEN"]["required"] is True
    assert form["DEMO_HUB_URL"]["required"] is True and form["DEMO_HUB_TOKEN"]["is_set"] is False


def test_missing_required_secret_is_refused_before_download(client, auth, gh):
    publish_with_hooks(gh, required_token=True)
    before = gh.count("codeload.github.com")
    r = install(client, auth, settings_={"DEMO_HUB_URL": "https://demo.example.org"})
    assert r.status_code == 422 and "DEMO_HUB_TOKEN" in r.json()["detail"]
    assert gh.count("codeload.github.com") == before and plugin_registry.get("demo_hub") is None


def test_install_stores_the_secret_encrypted_and_reports_the_test(client, auth, gh):
    publish_with_hooks(gh)
    r = install(client, auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active"] is True
    assert body["connection_test"] == {"ok": True, "level": "ok", "message": "Connected, token valid"}
    with SessionLocal() as db:
        row = db.get(ConfigOverride, "DEMO_HUB_TOKEN")
        assert row.secret is True and TOKEN not in row.value and decrypt(row.value) == TOKEN
    assert TOKEN not in r.text and TOKEN not in client.get("/api/admin/settings", headers=auth).text


def test_failing_test_is_reported_but_keeps_the_installation(client, auth, gh):
    publish_with_hooks(gh)
    r = install(client, auth, settings_={"DEMO_HUB_URL": "https://demo.example.org", "DEMO_HUB_TOKEN": "wrong"})
    assert r.status_code == 200
    assert r.json()["connection_test"] == {"ok": False, "level": "error",
                                           "message": "Token rejected by https://demo.example.org"}
    assert plugin_registry.get("demo_hub") is not None  # the admin can fix the settings


def test_plugin_without_a_test_reports_none(client, auth, gh):
    gh.publish(SHA1, repo_files())
    assert install(client, auth).json()["connection_test"] is None


def test_settings_screen_test_before_saving_uses_stored_secret_when_empty(client, auth, gh):
    publish_with_hooks(gh)
    assert install(client, auth).status_code == 200
    ok = client.post("/api/admin/plugins/demo_hub/test", headers=auth,
                     json={"values": {"DEMO_HUB_URL": "https://other.example.org", "DEMO_HUB_TOKEN": ""}})
    assert ok.json() == {"ok": True, "level": "ok", "message": "Connected, token valid"}
    bad = client.post("/api/admin/plugins/demo_hub/test", headers=auth,
                      json={"values": {"DEMO_HUB_URL": "https://other.example.org", "DEMO_HUB_TOKEN": "typo"}})
    assert bad.json()["ok"] is False and "other.example.org" in bad.json()["message"]
    with SessionLocal() as db:  # testing saved nothing
        assert decrypt(db.get(ConfigOverride, "DEMO_HUB_TOKEN").value) == TOKEN
    assert client.get("/api/modules", headers=auth).json()["plugins"]  # still serving


def test_installed_plugin_hooks_run_only_while_it_is_set_up(client, auth, gh):
    publish_with_hooks(gh)
    assert install(client, auth).status_code == 200
    plugin = plugin_registry.get("demo_hub")
    cards = client.get("/api/today", headers=auth).json()["plugin_cards"]
    assert [c["key"] for c in cards] == ["plugin:demo_hub:s"]
    assert cards[0]["image"] == "/api/plugins/demo_hub/items"
    jobs.reset()
    assert "demo_hub" in asyncio.run(jobs.run_due(wait=True)) and type(plugin).runs == 1

    # An admin clears the required address: the plugin needs setup again and none of its hooks run
    client.put("/api/admin/settings", headers=auth, json={"values": {"DEMO_HUB_URL": ""}})
    with SessionLocal() as db:
        db.query(ConfigOverride).filter(ConfigOverride.key == "DEMO_HUB_URL").delete()
        db.commit()
    from app.services import config_store

    config_store._apply("DEMO_HUB_URL", "")  # noqa: SLF001
    view = next(p for p in client.get("/api/modules", headers=auth).json()["plugins"] if p["id"] == "demo_hub")
    assert view["needs_setup"] is True and view["active"] is False
    assert client.get("/api/today", headers=auth).json()["plugin_cards"] == []
    jobs.reset()
    assert "demo_hub" not in asyncio.run(jobs.run_due(wait=True)) and type(plugin).runs == 1
    jobs.reset()
