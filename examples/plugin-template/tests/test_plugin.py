"""Tests for the example plugin. Run with the hub's backend on the path:

    pip install pytest respx httpx fastapi
    DATA_DIR=$(mktemp -d) PYTHONPATH=/path/to/familienhub/backend pytest

The hub itself is never started: the plugin's router is mounted on a small FastAPI app, the login is
replaced, and the notes service is simulated with respx. Real services are never called in tests.
"""

import json
from pathlib import Path

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.plugins.manifest import validate_manifest
from fh_plugin_example_notes.plugin import ExampleNotesPlugin

ROOT = Path(__file__).resolve().parents[1]
NOTES = "https://notes.example.org"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("EXAMPLE_NOTES_URL", NOTES)  # get_setting also reads the environment
    monkeypatch.delenv("EXAMPLE_NOTES_TOKEN", raising=False)
    app = FastAPI()
    for router in ExampleNotesPlugin().routers():
        app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: object()  # any logged-in user
    return TestClient(app)


@pytest.fixture
def notes():
    with respx.mock(using="httpx", assert_all_called=False) as service:
        service.route(host="testserver").pass_through()  # the test client itself
        yield service


def test_manifest_is_valid_and_matches_the_code():
    manifest = validate_manifest(json.loads((ROOT / "familienhub-plugin.json").read_text()))
    plugin = ExampleNotesPlugin()
    assert plugin.id == manifest["id"]
    assert manifest["entry_point"] == "fh_plugin_example_notes.plugin:ExampleNotesPlugin"
    assert {s.key for s in plugin.settings} <= {s["key"] for s in manifest["settings"]}
    assert set(plugin.capabilities) <= set(manifest["capabilities"])
    for router in plugin.routers():
        assert all(r.path.startswith(f"/api/plugins/{manifest['id']}/") for r in router.routes)


def test_items_from_the_service(client, notes, monkeypatch):
    monkeypatch.setenv("EXAMPLE_NOTES_TOKEN", "secret-token")
    route = notes.get(f"{NOTES}/notes").mock(return_value=httpx.Response(200, json=[{"id": 1, "title": "Milk"}, "junk"]))
    body = client.get("/api/plugins/example_notes/items").json()
    assert body == {"status": "ok", "error": None, "items": [{"id": "1", "title": "Milk"}]}
    assert route.calls.last.request.headers["Authorization"] == "Bearer secret-token"


def test_not_configured_is_empty_not_an_error(client, notes, monkeypatch):
    monkeypatch.delenv("EXAMPLE_NOTES_URL")
    assert client.get("/api/plugins/example_notes/items").json() == {"status": "not_configured", "error": None, "items": []}


@pytest.mark.parametrize("answer", [
    httpx.Response(500),
    httpx.Response(200, text="not json"),
    httpx.Response(200, json={"unexpected": "shape"}),
    httpx.ConnectError("down"),
])
def test_a_broken_service_never_breaks_the_app(client, notes, answer):
    notes.get(f"{NOTES}/notes").mock(side_effect=[answer])
    response = client.get("/api/plugins/example_notes/items")
    assert response.status_code == 200
    assert response.json() == {"status": "unavailable", "error": "Der Notiz-Dienst ist nicht erreichbar", "items": []}


def test_texts_follow_the_app_language(client, notes):
    notes.get(f"{NOTES}/notes").mock(return_value=httpx.Response(503))
    body = client.get("/api/plugins/example_notes/items", headers={"X-App-Language": "en"}).json()
    assert body["error"] == "The notes service is not reachable"
