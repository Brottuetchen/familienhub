"""examples/plugin-template stays valid: its manifest passes the installer's validation, it loads exactly like an
installed plugin, and its own tests (the ones plugin authors run) pass."""

import json
import os
import pathlib
import subprocess
import sys

import httpx
import pytest
import respx

from app.core.database import SessionLocal
from app.main import app
from app.models.config import ConfigOverride
from app.plugins import installer
from app.plugins.manifest import validate_manifest
from app.plugins.registry import plugin_registry
from app.services import config_store

TEMPLATE = pathlib.Path(__file__).resolve().parents[2] / "examples" / "plugin-template"
NOTES = "https://notes.example.org"


def _manifest():
    return validate_manifest(json.loads((TEMPLATE / "familienhub-plugin.json").read_text()))


@pytest.fixture
def template_plugin(client):
    plugin = installer.load_plugin(app, _manifest(), TEMPLATE)  # the same checks as after a real install
    yield plugin
    installer.unload_plugin(app, "example_notes")
    with SessionLocal() as db:
        db.query(ConfigOverride).filter(ConfigOverride.key.like("EXAMPLE_NOTES_%")).delete(synchronize_session=False)
        db.commit()
    for key in [k for k in config_store._extra if k.startswith("EXAMPLE_NOTES_")]:  # noqa: SLF001
        config_store._extra.pop(key)  # noqa: SLF001


def test_template_manifest_is_valid():
    manifest = _manifest()
    assert manifest["id"] == "example_notes" and manifest["package"] == "."
    assert [s["key"] for s in manifest["settings"]] == ["EXAMPLE_NOTES_URL", "EXAMPLE_NOTES_TOKEN"]
    assert manifest["settings"][1]["secret"] is True
    for path in ("README.md", "pyproject.toml", "fh_plugin_example_notes/plugin.py", "tests/test_plugin.py"):
        assert (TEMPLATE / path).is_file(), path
    assert 'example_notes = "fh_plugin_example_notes.plugin:ExampleNotesPlugin"' in (TEMPLATE / "pyproject.toml").read_text()


def test_template_works_as_an_installed_plugin(client, auth, template_plugin):
    assert plugin_registry.get("example_notes") is template_plugin and template_plugin.active is False  # URL missing
    assert client.get("/api/plugins/example_notes/items").status_code == 401  # login required
    empty = client.get("/api/plugins/example_notes/items", headers=auth).json()
    assert empty == {"status": "not_configured", "error": None, "items": []}

    with SessionLocal() as db:
        config_store.save_overrides(db, {"EXAMPLE_NOTES_URL": NOTES, "EXAMPLE_NOTES_TOKEN": "tok"})
    assert template_plugin.active is True
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        route = http.get(f"{NOTES}/notes").mock(return_value=httpx.Response(200, json=[{"id": 7, "title": "Bread"}]))
        body = client.get("/api/plugins/example_notes/items", headers=auth).json()
        assert body == {"status": "ok", "error": None, "items": [{"id": "7", "title": "Bread"}]}
        assert route.calls.last.request.headers["Authorization"] == "Bearer tok"
        route.mock(return_value=httpx.Response(500))
        down = client.get("/api/plugins/example_notes/items", headers={**auth, "X-App-Language": "en"})
        assert down.status_code == 200
        assert down.json() == {"status": "unavailable", "error": "The notes service is not reachable", "items": []}


def test_template_own_tests_pass(tmp_path):
    """What the README tells authors to run."""
    backend = pathlib.Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(backend), "DATA_DIR": str(tmp_path / "data"), "SECRET_KEY": "t" * 40,
           "DATABASE_URL": f"sqlite:///{tmp_path}/t.db", "PYTHONDONTWRITEBYTECODE": "1"}
    run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-W", "ignore::DeprecationWarning"],
                         cwd=TEMPLATE, env=env, capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stdout[-2500:] + run.stderr[-1500:]
    assert "passed" in run.stdout
