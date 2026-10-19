"""Plugin and theme store (#7): index parsing, merged sources, pinned installs, updates, custom sources.

GitHub (api, raw, codeload) is simulated with respx through the installer test's ``FakeGitHub``; the store's own
index, theme and screenshot files are served by its ``override`` hook. The mock only serves bytes: what the hub
shows, installs and refuses is decided by the hub's code.
"""

import json
import pathlib

import httpx
import pytest

from app.core.database import SessionLocal
from app.models.installed_plugin import InstalledPlugin
from app.models.store_source import StoreSource
from app.models.theme import Theme
from app.store import index as idx
from app.store import service
from tests.test_plugin_installer import (SHA1, SHA2, URL, FakeGitHub, _login, gh, offline_pip, repo_files)  # noqa: F401

INDEX_URL = "https://raw.githubusercontent.com/acme/store/main/index.json"
ALLOWED = frozenset({"raw.githubusercontent.com"})
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
THEME = {"name": "Waldgrün", "colors": {"primary": "#2E7D32", "secondary": "#A5D6A7", "background": "#0B1F0E",
                                         "surface": "#13301A", "surfaceHigh": "#1C4224", "border": "#2C5A35"}}
THEME_SHA = "c" * 40
THEME_SHA2 = "d" * 40


def plugin_entry(**kw):
    return {"type": "plugin", "id": "demo_hub", "name": {"de": "Demo-Plugin", "en": "Demo plugin"},
            "summary": {"de": "Kurz", "en": "Short"}, "description": {"de": "Lang", "en": "Long"},
            "author": "Acme", "repo": URL, "sha": SHA1, "version": "1.0.0",
            "screenshots": ["screenshots/demo_hub/1.png"], "tags": ["demo"], **kw}


def theme_entry(**kw):
    return {"type": "theme", "id": "waldgruen", "name": "Waldgrün", "summary": {"de": "Grün", "en": "Green"},
            "author": "Acme", "repo": "https://github.com/acme/themes", "path": "wald", "sha": THEME_SHA,
            "version": "1.0.0", **kw}


class Store:
    """The store repositories as served by (fake) raw.githubusercontent.com."""

    def __init__(self, fake: FakeGitHub):
        self.indexes = {"/acme/store/main/index.json": self.doc([plugin_entry(), theme_entry()])}
        self.files = {"/acme/store/main/screenshots/demo_hub/1.png": PNG}
        self.themes = {f"/acme/themes/{THEME_SHA}/wald/theme.json": json.dumps(THEME).encode()}
        self.down = False
        fake.override = self.handle
        self.fake = fake

    @staticmethod
    def doc(entries, version=1):
        return json.dumps({"version": version, "name": "Test store", "entries": entries}).encode()

    def handle(self, request: httpx.Request):
        if request.url.host != "raw.githubusercontent.com":
            return None
        path = request.url.path
        if self.down and path.endswith("index.json"):
            return httpx.Response(503)
        for table in (self.indexes, self.files, self.themes):
            if path in table:
                return httpx.Response(200, content=table[path])
        return None


@pytest.fixture
def store(gh, monkeypatch):  # noqa: F811
    from app.config import settings

    monkeypatch.setattr(settings, "store_index_url", INDEX_URL)
    service.clear_cache()
    gh.publish(SHA1, repo_files("demo_hub", "1.0.0"), head=False)
    s = Store(gh)
    yield s
    service.clear_cache()
    with SessionLocal() as db:
        db.query(StoreSource).delete()
        db.query(Theme).delete()
        db.commit()


def items(client, auth, lang="de", **params):
    r = client.get("/api/admin/store", headers={**auth, "X-App-Language": lang}, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def ref(source="official", kind="plugin", entry_id="demo_hub"):
    return {"source": source, "type": kind, "id": entry_id}


def install_body(sha=SHA1, **kw):
    return {**ref(), "sha": sha, "settings": {"DEMO_HUB_URL": "https://demo.example.org"}, **kw}


# --- Index format ---

def parse(entries, **kw):
    return idx.parse_index(Store.doc(entries, **kw), INDEX_URL, ALLOWED)


def test_example_index_validates():
    path = pathlib.Path(__file__).resolve().parents[2] / "examples" / "store" / "index.json"
    parsed = idx.parse_index(path.read_bytes(), INDEX_URL, ALLOWED)
    assert parsed.skipped == []
    assert {e.type for e in parsed.entries} == {"theme", "plugin"}
    assert len(parsed.entries) == 6
    assert parsed.entries[0].screenshots[0] == "https://raw.githubusercontent.com/acme/store/main/screenshots/clean-cards/1.png"


def test_valid_entries_are_normalised():
    e = parse([plugin_entry(), theme_entry()]).entries
    assert e[0].screenshots == ("https://raw.githubusercontent.com/acme/store/main/screenshots/demo_hub/1.png",)
    assert e[1].name == {"de": "Waldgrün", "en": "Waldgrün"} and e[1].description == e[1].summary
    assert idx.pick({"de": "Nur Deutsch"}, "en") == "Nur Deutsch"  # fallback to the other language


@pytest.mark.parametrize("change", [
    {"type": "widget"}, {"id": "Bad Id"}, {"id": "weather"}, {"sha": "abc"}, {"sha": "A" * 40}, {"version": "latest"},
    {"repo": "https://gitlab.com/a/b"}, {"repo": "https://github.com/a/b/tree/main"}, {"surprise": 1},
    {"name": {"fr": "x"}}, {"summary": "x" * 141}, {"author": ""}, {"tags": ["x"] * 9},
    {"screenshots": ["../x.png"]}, {"screenshots": ["/abs.png"]}, {"screenshots": ["shot.svg"]},
    {"screenshots": ["https://evil.example/a.png"]}, {"screenshots": ["http://raw.githubusercontent.com/a.png"]},
    {"screenshots": ["a.png"] * 9}, {"path": "../up"}, {"min_hub_version": "soon"},
])
def test_invalid_entry_is_skipped_with_reason_and_others_survive(change):
    parsed = parse([plugin_entry(**change), theme_entry()])
    assert [e.id for e in parsed.entries] == ["waldgruen"]
    assert len(parsed.skipped) == 1 and parsed.skipped[0]["reason"]


def test_duplicate_and_missing_fields_are_skipped():
    broken = plugin_entry()
    del broken["sha"]
    parsed = parse([plugin_entry(), plugin_entry(), broken, "text"])
    assert len(parsed.entries) == 1 and len(parsed.skipped) == 3


@pytest.mark.parametrize("body", [b"{nope", b"[]", json.dumps({"version": 2, "entries": []}).encode(),
                                  json.dumps({"version": 1}).encode(), json.dumps({"version": 1, "entries": [], "x": 1}).encode(),
                                  b" " * (idx.MAX_INDEX_BYTES + 1)])
def test_bad_index_is_rejected_as_a_whole(body):
    with pytest.raises(idx.IndexError_):
        idx.parse_index(body, INDEX_URL, ALLOWED)


# --- Listing ---

def test_store_is_admin_only(client, auth, store):
    assert client.get("/api/admin/store").status_code == 401
    partner = _login(client, "store_partner", "partner")
    for method, path in (("get", "/api/admin/store"), ("get", "/api/admin/store/sources"),
                         ("post", "/api/admin/store/install"), ("post", "/api/admin/store/inspect"),
                         ("post", "/api/admin/store/sources"), ("delete", "/api/admin/store/sources/1"),
                         ("get", "/api/admin/store/screenshot/official/plugin/demo_hub/0")):
        assert getattr(client, method)(path, headers=partner).status_code == 403, path


def test_listing_official_entries_are_verified_and_localised(client, auth, store):
    data = items(client, auth, "en")
    assert [s["id"] for s in data["sources"]] == ["official"] and data["sources"][0]["verified"] is True
    plugin = next(i for i in data["items"] if i["type"] == "plugin")
    assert plugin["name"] == "Demo plugin" and plugin["summary"] == "Short" and plugin["verified"] is True
    assert plugin["state"] == "available" and plugin["sha"] == SHA1 and plugin["compatible"] is True
    assert plugin["screenshots"] == ["/api/admin/store/screenshot/official/plugin/demo_hub/0"]
    assert items(client, auth, "de")["items"][0]["name"] in ("Demo-Plugin", "Waldgrün")


def test_index_is_cached_and_refresh_bypasses_the_cache(client, auth, store):
    items(client, auth)
    items(client, auth)
    assert store.fake.calls.count(INDEX_URL) == 1
    items(client, auth, refresh="true")
    assert store.fake.calls.count(INDEX_URL) == 2


def test_unreachable_store_gives_empty_list_and_status(client, auth, store):
    store.down = True
    data = items(client, auth)
    assert data["items"] == [] and data["sources"][0]["status"] == "unreachable"
    store.down = False
    store.indexes["/acme/store/main/index.json"] = b"{broken"
    data = items(client, auth, refresh="true")
    assert data["items"] == [] and data["sources"][0]["status"] == "invalid"


def test_failed_refresh_keeps_last_good_copy(client, auth, store):
    assert len(items(client, auth)["items"]) == 2
    store.down = True
    data = items(client, auth, refresh="true")
    assert len(data["items"]) == 2 and data["sources"][0]["stale"] is True


def test_empty_official_url_switches_official_source_off(client, auth, store, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "store_index_url", "")
    assert items(client, auth) == {"installer_enabled": True, "sources": [], "items": []}


def test_skipped_entries_are_reported_on_the_source(client, auth, store):
    store.indexes["/acme/store/main/index.json"] = Store.doc([plugin_entry(), plugin_entry(id="weather")])
    source = items(client, auth)["sources"][0]
    assert source["entries"] == 1 and source["skipped"][0]["id"] == "weather"


# --- Installing a plugin ---

def test_install_uses_the_pinned_commit_not_the_branch_head(client, auth, store):
    store.fake.publish(SHA2, repo_files("demo_hub", "2.0.0"), head=True)  # the branch moved on, the index did not
    r = client.post("/api/admin/store/install", headers=auth, json=install_body())
    assert r.status_code == 200, r.text
    assert r.json()["sha"] == SHA1 and r.json()["version"] == "1.0.0" and r.json()["updated"] is False
    with SessionLocal() as db:
        row = db.get(InstalledPlugin, "demo_hub")
        assert row.sha == SHA1 and row.store_source == "official"
    assert any(f"/tar.gz/{SHA1}" in u for u in store.fake.calls)
    assert not any(SHA2 in u for u in store.fake.calls)
    assert not any(u.startswith("https://api.github.com") for u in store.fake.calls)  # nothing was re-resolved
    assert items(client, auth)["items"][0]["state"] in ("installed", "available")
    plugin = next(i for i in items(client, auth)["items"] if i["type"] == "plugin")
    assert plugin["state"] == "installed" and plugin["installed_version"] == "1.0.0"


def test_inspect_shows_manifest_at_pinned_commit(client, auth, store):
    r = client.post("/api/admin/store/inspect", headers=auth, json=ref())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sha"] == SHA1 and body["manifest"]["id"] == "demo_hub" and body["verified"] is True
    assert [s["key"] for s in body["settings"]][0] == "DEMO_HUB_URL"


def test_update_is_detected_and_installed_on_request_only(client, auth, store):
    assert client.post("/api/admin/store/install", headers=auth, json=install_body()).status_code == 200
    store.fake.publish(SHA2, repo_files("demo_hub", "2.0.0"), head=True)
    store.indexes["/acme/store/main/index.json"] = Store.doc([plugin_entry(sha=SHA2, version="2.0.0")])
    plugin = items(client, auth, refresh="true")["items"][0]
    assert plugin["state"] == "update" and plugin["installed_version"] == "1.0.0" and plugin["version"] == "2.0.0"
    with SessionLocal() as db:
        assert db.get(InstalledPlugin, "demo_hub").sha == SHA1  # listing never updates by itself
    r = client.post("/api/admin/store/install", headers=auth, json=install_body(sha=SHA2))
    assert r.status_code == 200 and r.json()["updated"] is True and r.json()["version"] == "2.0.0"
    assert items(client, auth)["items"][0]["state"] == "installed"


def test_install_refuses_a_commit_the_admin_did_not_review(client, auth, store):
    store.indexes["/acme/store/main/index.json"] = Store.doc([plugin_entry(sha=SHA2, version="2.0.0")])
    service.clear_cache()
    r = client.post("/api/admin/store/install", headers=auth, json=install_body(sha=SHA1))
    assert r.status_code == 409
    assert not any("codeload" in u for u in store.fake.calls)


def test_install_checks_that_the_repository_matches_the_entry_id(client, auth, store):
    store.fake.publish(SHA1, repo_files("other_demo", "1.0.0"), head=False)
    r = client.post("/api/admin/store/install", headers=auth, json=install_body())
    assert r.status_code == 422 and "other_demo" in r.text
    with SessionLocal() as db:
        assert db.get(InstalledPlugin, "demo_hub") is None


def test_unknown_entry_is_404(client, auth, store):
    assert client.post("/api/admin/store/install", headers=auth, json=install_body(id="nothing")).status_code == 404
    assert client.post("/api/admin/store/inspect", headers=auth, json=ref(source="custom-9")).status_code == 404


def test_listing_marks_a_plugin_from_another_repository_as_conflict(client, auth, store):
    store.fake.publish(SHA1, repo_files("demo_hub", "1.0.0"), head=True)
    assert client.post("/api/plugins/install", headers=auth, json={
        "url": URL, "sha": SHA1, "settings": {"DEMO_HUB_URL": "https://demo.example.org"}}).status_code == 200
    store.indexes["/acme/store/main/index.json"] = Store.doc([plugin_entry(repo="https://github.com/other/demo")])
    assert items(client, auth, refresh="true")["items"][0]["state"] == "conflict"


# --- Themes ---

def test_theme_install_update_from_pinned_commit(client, auth, store):
    body = {**ref(kind="theme", entry_id="waldgruen"), "sha": THEME_SHA}
    r = client.post("/api/admin/store/install", headers=auth, json=body)
    assert r.status_code == 200, r.text
    assert r.json()["theme"]["name"] == "Waldgrün" and r.json()["updated"] is False
    assert any(f"/acme/themes/{THEME_SHA}/wald/theme.json" in u for u in store.fake.calls)
    with SessionLocal() as db:
        row = db.query(Theme).filter(Theme.store_id == "waldgruen").one()
        assert row.store_sha == THEME_SHA and row.store_source == "official"
    assert [i for i in items(client, auth)["items"] if i["type"] == "theme"][0]["state"] == "installed"
    # a new commit in the index → update available → one click
    store.themes[f"/acme/themes/{THEME_SHA2}/wald/theme.json"] = json.dumps(
        {**THEME, "colors": {**THEME["colors"], "primary": "#111111"}}).encode()
    store.indexes["/acme/store/main/index.json"] = Store.doc([theme_entry(sha=THEME_SHA2, version="1.1.0")])
    theme = items(client, auth, refresh="true")["items"][0]
    assert theme["state"] == "update" and theme["installed_version"] == "1.0.0"
    r = client.post("/api/admin/store/install", headers=auth, json={**body, "sha": THEME_SHA2})
    assert r.status_code == 200 and r.json()["updated"] is True
    with SessionLocal() as db:
        assert db.query(Theme).count() == 1  # updated in place
        assert json.loads(db.query(Theme).one().data)["colors"]["primary"] == "#111111"


def test_theme_with_invalid_colours_is_refused(client, auth, store):
    store.themes[f"/acme/themes/{THEME_SHA}/wald/theme.json"] = json.dumps(
        {**THEME, "colors": {**THEME["colors"], "primary": "red"}}).encode()
    r = client.post("/api/admin/store/install", headers=auth,
                    json={**ref(kind="theme", entry_id="waldgruen"), "sha": THEME_SHA})
    assert r.status_code == 422
    with SessionLocal() as db:
        assert db.query(Theme).count() == 0


def test_builtin_theme_name_counts_as_installed(client, auth, store):
    store.indexes["/acme/store/main/index.json"] = Store.doc([theme_entry(name="Liquid Glass")])
    assert items(client, auth, refresh="true")["items"][0]["state"] == "installed"


# --- Custom sources ---

CUSTOM_INDEX = "/mine/extras/main/index.json"


def add_source(client, auth, url="https://github.com/mine/extras/tree/main", acknowledge=True):
    return client.post("/api/admin/store/sources", headers=auth, json={"url": url, "acknowledge": acknowledge})


def test_custom_source_lifecycle_and_unverified_flag(client, auth, store):
    store.indexes[CUSTOM_INDEX] = Store.doc([plugin_entry(name="Eigenes", id="mine_x")])
    r = add_source(client, auth)
    assert r.status_code == 201, r.text
    source = r.json()
    assert source["verified"] is False and source["removable"] is True and source["status"] == "ok"
    data = items(client, auth)
    custom = [i for i in data["items"] if i["source"] == source["id"]]
    assert len(custom) == 1 and custom[0]["verified"] is False
    assert all(i["verified"] for i in data["items"] if i["source"] == "official")
    assert data["items"][-1]["verified"] is False  # verified entries first
    assert add_source(client, auth).status_code == 409
    assert client.get("/api/admin/store/sources", headers=auth).json()["items"][1]["id"] == source["id"]
    assert client.delete(f"/api/admin/store/sources/{source['id'].split('-')[1]}", headers=auth).status_code == 200
    assert [s["id"] for s in items(client, auth)["sources"]] == ["official"]
    assert client.delete("/api/admin/store/sources/999", headers=auth).status_code == 404


def test_adding_a_source_needs_acknowledgement_and_a_valid_index(client, auth, store):
    store.indexes[CUSTOM_INDEX] = Store.doc([plugin_entry(id="mine_x")])
    assert add_source(client, auth, acknowledge=False).status_code == 422
    assert add_source(client, auth, url="https://gitlab.com/mine/extras").status_code == 422
    assert add_source(client, auth, url="https://github.com/nobody/nothing").status_code == 422  # 404 → no index
    store.indexes["/mine/bad/HEAD/index.json"] = b"[]"
    assert add_source(client, auth, url="https://github.com/mine/bad").status_code == 422
    with SessionLocal() as db:
        assert db.query(StoreSource).count() == 0


def test_installing_from_an_unverified_source_needs_the_warning_confirmed(client, auth, store):
    store.indexes[CUSTOM_INDEX] = Store.doc([plugin_entry(id="demo_hub")])
    sid = add_source(client, auth).json()["id"]
    body = install_body(**{"source": sid})
    r = client.post("/api/admin/store/install", headers=auth, json=body)
    assert r.status_code == 422 and not any("codeload" in u for u in store.fake.calls)
    r = client.post("/api/admin/store/install", headers=auth, json={**body, "acknowledge_unverified": True})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert db.get(InstalledPlugin, "demo_hub").store_source == sid


def test_unreachable_custom_source_does_not_hide_the_official_one(client, auth, store):
    store.indexes[CUSTOM_INDEX] = Store.doc([plugin_entry(id="mine_x")])
    add_source(client, auth)
    del store.indexes[CUSTOM_INDEX]
    service.clear_cache()  # no last good copy to fall back on
    data = items(client, auth)
    assert [s["status"] for s in data["sources"]] == ["ok", "invalid"] and len(data["items"]) == 2


# --- Screenshots ---

def test_screenshot_is_proxied_with_type_checks(client, auth, store):
    path = "/api/admin/store/screenshot/official/plugin/demo_hub/0"
    r = client.get(path, headers=auth)
    assert r.status_code == 200 and r.content == PNG and r.headers["content-type"] == "image/png"
    assert r.headers["x-content-type-options"] == "nosniff"
    client.get(path, headers=auth)
    assert sum("1.png" in u for u in store.fake.calls) == 1  # cached
    assert client.get(path.replace("/0", "/5"), headers=auth).status_code == 404
    assert client.get("/api/admin/store/screenshot/official/plugin/unknown/0", headers=auth).status_code == 404


@pytest.mark.parametrize("body", [b"<svg xmlns='http://www.w3.org/2000/svg'/>", b"<html>no</html>", PNG + b"0" * (2 * 1024 * 1024)])
def test_screenshot_refuses_non_images_and_oversize(client, auth, store, body):
    store.files["/acme/store/main/screenshots/demo_hub/1.png"] = body
    assert client.get("/api/admin/store/screenshot/official/plugin/demo_hub/0", headers=auth).status_code == 404


def test_only_listed_hosts_are_ever_contacted(client, auth, store):
    items(client, auth)
    client.get("/api/admin/store/screenshot/official/plugin/demo_hub/0", headers=auth)
    assert {httpx.URL(u).host for u in store.fake.calls} == {"raw.githubusercontent.com"}


def test_migration_head_is_unique():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = pathlib.Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    assert ScriptDirectory.from_config(cfg).get_heads() == ["f8a9b0c1d2e3"]

