"""Personal plugin settings: manifest field, storage with encrypted secrets, API, plugin API, cleanup."""

import json

import pytest

from app.config import settings
from app.core.crypto import decrypt
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.installed_plugin import InstalledPlugin
from app.models.plugin_user_setting import PluginUserSetting
from app.models.user import User
from app.plugins import Plugin, Setting
from app.plugins.api import get_personal_setting
from app.plugins.manifest import personal_settings_for, validate_manifest
from app.plugins.registry import plugin_registry
from app.services import personal_settings

MANIFEST = {"id": "recap_demo", "name": "Recap", "version": "1.0.0", "description": "d", "author": "a",
            "entry_point": "x.y:Z"}


class Recap(Plugin):
    def __init__(self, pid="pers_demo"):
        k = pid.upper()
        super().__init__(
            id=pid, name="Persönlich", description="Eigene Konten",
            personal_settings=(
                Setting(f"{k}_USER", "Benutzer", help="Dein Name dort"),
                Setting(f"{k}_TOKEN", "Zugangsschlüssel", secret=True, type="password"),
                Setting(f"{k}_DAYS", "Tage", required=False, type="number", default="30"),
                Setting(f"{k}_HOST", "Adresse", required=False, type="url"),
                Setting(f"{k}_FLAG", "Schalter", required=False, type="bool"),
            ))
        self.tested = None

    async def test_personal_settings(self, user, values):
        self.tested = (user.id, dict(values))
        return {"ok": values["PERS_DEMO_TOKEN"] == "tok-1", "level": "ok", "message": "geprüft"}


@pytest.fixture
def plug():
    plugin = Recap()
    assert plugin_registry.register(plugin)
    yield plugin
    plugin_registry.unregister(plugin.id)
    with SessionLocal() as db:
        db.query(PluginUserSetting).delete()
        db.commit()


def person(client, name, role="partner"):
    with SessionLocal() as db:
        if not db.query(User).filter(User.username == name).first():
            db.add(User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"),
                        role=role, full_name=name.title()))
            db.commit()
        uid = db.query(User).filter(User.username == name).first().id
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}, uid


URL = "/api/plugins/pers_demo/personal-settings"


# --- manifest ---

def manifest(**extra):
    return validate_manifest({**MANIFEST, **extra})


def test_manifest_accepts_personal_settings_with_the_settings_schema():
    m = manifest(personal_settings=[
        {"key": "RECAP_DEMO_USER", "label": {"de": "Benutzer", "en": "User"}},
        {"key": "RECAP_DEMO_TOKEN", "label": "Token", "type": "password", "required": False},
        {"key": "RECAP_DEMO_DAYS", "label": "Days", "type": "number", "default": 30, "example": "30"}])
    assert [s["key"] for s in m["personal_settings"]] == ["RECAP_DEMO_USER", "RECAP_DEMO_TOKEN", "RECAP_DEMO_DAYS"]
    assert m["personal_settings"][1]["secret"] is True
    assert m["personal_settings"][2]["default"] == "30"
    assert [s.key for s in personal_settings_for(m)] == ["RECAP_DEMO_USER", "RECAP_DEMO_TOKEN", "RECAP_DEMO_DAYS"]
    assert personal_settings_for(m)[1].secret is True and personal_settings_for(m)[2].type == "number"
    assert manifest()["personal_settings"] == [] and manifest()["pages"] == []


@pytest.mark.parametrize("bad", [
    [{"key": "OTHER_USER", "label": "x"}],                                   # wrong prefix
    [{"key": "RECAP_DEMO_X", "label": "x", "bogus": 1}],                     # unknown field
    [{"key": "RECAP_DEMO_X", "label": "x", "type": "secret"}],               # unknown type
    [{"key": "RECAP_DEMO_X", "label": "x", "secret": True, "default": "a"}],  # secret with default
    [{"key": "RECAP_DEMO_X", "label": "x"}, {"key": "RECAP_DEMO_X", "label": "y"}],   # duplicate
    [{"key": f"RECAP_DEMO_K{i}", "label": "x"} for i in range(21)],          # too many
    "nope",
])
def test_manifest_rejects_bad_personal_settings(bad):
    with pytest.raises(ValueError):
        manifest(personal_settings=bad)


def test_manifest_rejects_a_key_shared_with_settings():
    with pytest.raises(ValueError):
        manifest(settings=[{"key": "RECAP_DEMO_URL", "label": "x"}],
                 personal_settings=[{"key": "RECAP_DEMO_URL", "label": "x"}])


# --- API ---

def test_form_lists_fields_and_never_a_secret(client, plug):
    headers, _ = person(client, "pers_a")
    body = client.get(URL, headers=headers).json()
    assert body["id"] == "pers_demo" and body["has_test"] is True
    fields = {f["key"]: f for f in body["fields"]}
    assert fields["PERS_DEMO_TOKEN"]["secret"] is True and fields["PERS_DEMO_TOKEN"]["is_set"] is False
    assert fields["PERS_DEMO_DAYS"]["value"] == "30" and fields["PERS_DEMO_DAYS"]["type"] == "number"
    items = client.get("/api/plugins/personal-settings", headers=headers).json()["items"]
    assert [i["id"] for i in items] == ["pers_demo"]


def test_save_encrypts_secret_and_reports_only_that_it_is_set(client, plug):
    headers, uid = person(client, "pers_a")
    r = client.put(URL, headers=headers, json={"values": {"PERS_DEMO_USER": "anna", "PERS_DEMO_TOKEN": "tok-1"}})
    assert r.status_code == 200, r.text
    assert "tok-1" not in r.text
    fields = {f["key"]: f for f in r.json()["fields"]}
    assert fields["PERS_DEMO_USER"]["value"] == "anna" and fields["PERS_DEMO_TOKEN"]["is_set"] is True
    assert fields["PERS_DEMO_TOKEN"]["value"] == ""
    assert "tok-1" not in client.get(URL, headers=headers).text
    with SessionLocal() as db:
        row = db.get(PluginUserSetting, ("pers_demo", uid, "PERS_DEMO_TOKEN"))
        assert row.secret is True and row.value != "tok-1" and decrypt(row.value) == "tok-1"
        assert db.get(PluginUserSetting, ("pers_demo", uid, "PERS_DEMO_USER")).value == "anna"


def test_empty_secret_keeps_the_stored_value_and_empty_plain_value_clears_it(client, plug):
    headers, uid = person(client, "pers_a")
    client.put(URL, headers=headers, json={"values": {"PERS_DEMO_USER": "anna", "PERS_DEMO_TOKEN": "tok-1",
                                                      "PERS_DEMO_DAYS": "7"}})
    r = client.put(URL, headers=headers, json={"values": {"PERS_DEMO_USER": "anna", "PERS_DEMO_TOKEN": "",
                                                          "PERS_DEMO_DAYS": ""}})
    assert r.status_code == 200
    with SessionLocal() as db:
        assert personal_settings.get_value(db, plug, uid, "PERS_DEMO_TOKEN") == "tok-1"
        assert personal_settings.get_value(db, plug, uid, "PERS_DEMO_DAYS") == "30"  # back to the default


def test_validation_unknown_key_missing_required_and_value_types(client, plug):
    headers, _ = person(client, "pers_a")
    assert client.put(URL, headers=headers, json={"values": {"PERS_DEMO_NOPE": "x"}}).status_code == 422
    r = client.put(URL, headers=headers, json={"values": {"PERS_DEMO_USER": "anna"}})
    assert r.status_code == 422 and "PERS_DEMO_TOKEN" in r.json()["detail"]  # token is required
    ok = {"PERS_DEMO_USER": "anna", "PERS_DEMO_TOKEN": "t"}
    assert client.put(URL, headers=headers, json={"values": {**ok, "PERS_DEMO_DAYS": "many"}}).status_code == 422
    assert client.put(URL, headers=headers, json={"values": {**ok, "PERS_DEMO_HOST": "ftp://x"}}).status_code == 422
    assert client.put(URL, headers=headers, json={"values": {**ok, "PERS_DEMO_USER": "a\nb"}}).status_code == 422
    assert client.put(URL, headers=headers, json={"values": {**ok, "PERS_DEMO_FLAG": True,
                                                              "PERS_DEMO_DAYS": 5}}).status_code == 200
    # nothing from the failed attempts was kept
    with SessionLocal() as db:
        assert db.query(PluginUserSetting).filter(PluginUserSetting.key == "PERS_DEMO_HOST").count() == 0


def test_people_have_separate_values(client, plug):
    a, ida = person(client, "pers_a")
    b, idb = person(client, "pers_b")
    client.put(URL, headers=a, json={"values": {"PERS_DEMO_USER": "anna", "PERS_DEMO_TOKEN": "ta"}})
    client.put(URL, headers=b, json={"values": {"PERS_DEMO_USER": "ben", "PERS_DEMO_TOKEN": "tb"}})
    assert get_personal_setting(ida, "PERS_DEMO_USER") == "anna"
    assert get_personal_setting(idb, "PERS_DEMO_USER") == "ben"
    assert get_personal_setting(idb, "PERS_DEMO_TOKEN") == "tb"
    assert client.get(URL, headers=a).json()["fields"][0]["value"] == "anna"


def test_unknown_inactive_or_setting_less_plugins_are_404(client, plug):
    headers, _ = person(client, "pers_a")
    assert client.get("/api/plugins/nothere/personal-settings", headers=headers).status_code == 404
    assert client.get("/api/plugins/weather/personal-settings", headers=headers).status_code == 404  # no personal settings
    settings.plugins_disabled = "pers_demo"
    try:
        assert client.get(URL, headers=headers).status_code == 404
        assert client.get("/api/plugins/personal-settings", headers=headers).json()["items"] == []
    finally:
        settings.plugins_disabled = ""


def test_requires_login_and_a_role_of_child_or_up(client, plug):
    assert client.get(URL).status_code in (401, 403)
    guest, _ = person(client, "pers_guest", role="guest")
    assert client.get(URL, headers=guest).status_code == 403
    child, _ = person(client, "pers_child", role="child")
    assert client.get(URL, headers=child).status_code == 200


# --- test hook ---

def test_test_hook_gets_typed_values_with_stored_secret_and_saves_nothing(client, plug):
    headers, uid = person(client, "pers_a")
    client.put(URL, headers=headers, json={"values": {"PERS_DEMO_USER": "anna", "PERS_DEMO_TOKEN": "tok-1"}})
    r = client.post(URL + "/test", headers=headers, json={"values": {"PERS_DEMO_USER": "neu", "PERS_DEMO_TOKEN": ""}})
    assert r.status_code == 200 and r.json() == {"ok": True, "level": "ok", "message": "geprüft"}
    assert plug.tested[0] == uid
    assert plug.tested[1]["PERS_DEMO_USER"] == "neu" and plug.tested[1]["PERS_DEMO_TOKEN"] == "tok-1"
    assert plug.tested[1]["PERS_DEMO_DAYS"] == "30"
    with SessionLocal() as db:
        assert personal_settings.get_value(db, plug, uid, "PERS_DEMO_USER") == "anna"
    bad = client.post(URL + "/test", headers=headers, json={"values": {"PERS_DEMO_TOKEN": "other"}})
    assert bad.json()["ok"] is False


def test_test_hook_failure_is_reported_without_details(client, plug):
    async def boom(user, values):
        raise RuntimeError("secret-in-message")

    plug.test_personal_settings = boom
    headers, _ = person(client, "pers_a")
    r = client.post(URL + "/test", headers=headers, json={"values": {}})
    assert r.status_code == 200 and r.json()["ok"] is False and "secret-in-message" not in r.text


def test_plugin_without_a_test_answers_with_a_note(client):
    class NoTest(Plugin):
        def __init__(self):
            super().__init__(id="pers_plain", name="Plain", personal_settings=(Setting("PERS_PLAIN_A", "A"),))

    plugin = NoTest()
    plugin_registry.register(plugin)
    try:
        headers, _ = person(client, "pers_a")
        r = client.post("/api/plugins/pers_plain/personal-settings/test", headers=headers, json={"values": {}})
        assert r.status_code == 200 and r.json()["level"] == "info"
        assert client.get("/api/plugins/pers_plain/personal-settings", headers=headers).json()["has_test"] is False
    finally:
        plugin_registry.unregister("pers_plain")


# --- plugin API ---

def test_get_personal_setting_edge_cases(client, plug):
    _, uid = person(client, "pers_a")
    assert get_personal_setting(uid, "PERS_DEMO_USER") is None                    # nothing stored
    assert get_personal_setting(uid, "PERS_DEMO_DAYS") == "30"                    # default
    assert get_personal_setting(uid, "UNDECLARED_KEY") is None
    assert get_personal_setting(True, "PERS_DEMO_USER") is None
    with SessionLocal() as db:
        personal_settings.save(db, plug, uid, {"PERS_DEMO_USER": "anna", "PERS_DEMO_TOKEN": "t"})
        assert get_personal_setting(uid, "PERS_DEMO_USER", db=db) == "anna"
        assert get_personal_setting(uid, "PERS_DEMO_USER", plugin_id="pers_demo") == "anna"
        assert get_personal_setting(uid, "PERS_DEMO_USER", plugin_id="weather") is None
    settings.plugins_disabled = "pers_demo"
    try:
        assert get_personal_setting(uid, "PERS_DEMO_USER") is None               # inactive plugin
    finally:
        settings.plugins_disabled = ""


# --- cleanup ---

def test_removing_an_installed_plugin_deletes_its_personal_settings(client, auth, plug):
    _, uid = person(client, "pers_a")
    with SessionLocal() as db:
        personal_settings.save(db, plug, uid, {"PERS_DEMO_USER": "anna", "PERS_DEMO_TOKEN": "t"})
        other = PluginUserSetting(plugin_id="keepme", user_id=uid, key="KEEPME_A", value="1", secret=False)
        db.add(other)
        db.add(InstalledPlugin(id="pers_demo", repo_url="https://github.com/a/b", sha="a" * 40, version="1.0.0",
                               manifest=json.dumps(manifest())))
        db.commit()
    r = client.delete("/api/plugins/pers_demo", headers=auth)
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert db.query(PluginUserSetting).filter(PluginUserSetting.plugin_id == "pers_demo").count() == 0
        assert db.get(PluginUserSetting, ("keepme", uid, "KEEPME_A")) is not None


def test_deleting_a_person_deletes_their_personal_settings(client, auth, plug):
    headers, uid = person(client, "pers_gone")
    client.put(URL, headers=headers, json={"values": {"PERS_DEMO_USER": "x", "PERS_DEMO_TOKEN": "t"}})
    with SessionLocal() as db:
        assert db.query(PluginUserSetting).filter(PluginUserSetting.user_id == uid).count() == 2
    assert client.delete(f"/api/auth/users/{uid}", headers=auth).status_code == 200
    with SessionLocal() as db:
        assert db.query(PluginUserSetting).filter(PluginUserSetting.user_id == uid).count() == 0


def test_prune_drops_keys_an_update_no_longer_declares(client, plug):
    _, uid = person(client, "pers_a")
    with SessionLocal() as db:
        personal_settings.save(db, plug, uid, {"PERS_DEMO_USER": "x", "PERS_DEMO_TOKEN": "t"})
        plug.personal_settings = tuple(s for s in plug.personal_settings if s.key != "PERS_DEMO_USER")
        personal_settings.prune(db, plug)
        assert db.get(PluginUserSetting, ("pers_demo", uid, "PERS_DEMO_USER")) is None
        assert db.get(PluginUserSetting, ("pers_demo", uid, "PERS_DEMO_TOKEN")) is not None
