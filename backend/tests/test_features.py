"""Querschnitt: Standardwerte, Aufgaben-API, Web-App-Auslieferung, Downloads."""

import html
from pathlib import Path

import pytest

from app.config import Settings, settings


def test_defaults():
    defaults = Settings(_env_file=None)
    assert defaults.app_name == "Familienhub"
    assert defaults.disabled_plugins == []
    assert defaults.ha_shopping_todo == "todo.einkaufsliste"


def test_tasks_api_status_codes(client, auth, monkeypatch):
    """Aufgaben-API: {status, error, items} und Statuscodes laut BUILD_PROMPT WP 2b."""
    # Mock NextcloudTasksConnector für die neuen Task-Endpunkte
    from app.connectors.nextcloud_tasks_connector import NextcloudTasksConnector

    async def mock_get_tasks(self, view="all", include_done=False):
        return {"status": "ok", "error": None, "items": [{"id": "task", "title": "Test"}]}

    async def mock_create_task(self, title, notes=None, due=None, priority=None, assignee_id=None, list_kind=None):
        return {"id": "task", "title": title}

    async def mock_update_task(self, uid, **kwargs):
        return {"id": uid, "title": kwargs.get("title", "Test")}

    async def mock_complete_task(self, uid):
        return True

    async def mock_delete_task(self, uid):
        return True

    monkeypatch.setattr(NextcloudTasksConnector, "is_configured", property(lambda self: True))
    monkeypatch.setattr(NextcloudTasksConnector, "get_tasks", mock_get_tasks)
    monkeypatch.setattr(NextcloudTasksConnector, "create_task", mock_create_task)
    monkeypatch.setattr(NextcloudTasksConnector, "update_task", mock_update_task)
    monkeypatch.setattr(NextcloudTasksConnector, "complete_task", mock_complete_task)
    monkeypatch.setattr(NextcloudTasksConnector, "delete_task", mock_delete_task)

    # Prüfe neues API-Format: {status, error, items}
    result = client.get("/api/tasks", headers=auth).json()
    assert result["status"] == "ok"
    account = next(p["account"] for p in client.get("/api/tasks/providers", headers=auth).json()["items"] if p["id"] == "nextcloud")
    assert result["items"] == [{"id": "task", "title": "Test", "provider": "nextcloud", "account": account}]

    # Statuscodes exakt laut BUILD_PROMPT WP 2b: POST 201, PATCH/complete 200, DELETE 204
    for method, path, data, code in [("post", "/api/tasks", {"title": "Test"}, 201),
                                     ("patch", "/api/tasks/task", {"title": "Neu"}, 200),
                                     ("post", "/api/tasks/task/complete", {}, 200),
                                     ("delete", "/api/tasks/task", None, 204)]:
        response = client.request(method, path, headers=auth, **({"json": data} if data is not None else {}))
        assert response.status_code == code, (method, path, response.status_code)


@pytest.mark.parametrize("name", ["Familienhub", 'Unser <Hub> & "Familie"'])
def test_branding_and_manifest(monkeypatch, tmp_path, name):
    """Web-App (Flutter-Build): Titel und Manifest tragen APP_NAME, ohne Cache; Service Worker ohne Cache."""
    import json

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.main import mount_frontend

    (tmp_path / "index.html").write_text(
        '<html><head><meta name="apple-mobile-web-app-title" content="Familienhub">'
        "<title>Familienhub</title></head><body></body></html>", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(json.dumps({"name": "Familienhub", "short_name": "Familienhub",
                                                         "display": "standalone"}), encoding="utf-8")
    (tmp_path / "push-sw.js").write_text("self.addEventListener('push', () => {});", encoding="utf-8")
    (tmp_path / "main.dart.js").write_text("// app", encoding="utf-8")
    monkeypatch.setattr(settings, "app_name", name)
    web = FastAPI()
    assert mount_frontend(web, tmp_path) is True
    c = TestClient(web)
    for path in ("/", "/index.html"):
        r = c.get(path)
        assert r.status_code == 200
        assert f"<title>{html.escape(name)}</title>" in r.text
        assert r.headers["cache-control"] == "no-cache"
    manifest = c.get("/manifest.json").json()
    assert manifest["name"] == manifest["short_name"] == name
    assert manifest["display"] == "standalone"
    sw = c.get("/push-sw.js")
    assert sw.status_code == 200 and "javascript" in sw.headers["content-type"]
    assert sw.headers["cache-control"] == "no-cache"
    assert c.get("/main.dart.js").status_code == 200


def test_mount_frontend_without_build_returns_false(tmp_path):
    from fastapi import FastAPI

    from app.main import mount_frontend

    assert mount_frontend(FastAPI(), tmp_path) is False


def test_no_plex_runtime_defaults():
    root = Path(__file__).resolve().parents[2]
    paths = list((root / "backend/app").rglob("*.py")) + [root / ".env.example"]
    assert not [str(p.relative_to(root)) for p in paths if "plex" in p.read_text().lower()]


def test_downloads_served_only_when_configured(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.main import mount_downloads

    assert mount_downloads(FastAPI(), None) is False
    assert mount_downloads(FastAPI(), str(tmp_path / "fehlt")) is False

    (tmp_path / "index.html").write_text('<a href="familienhub-1.0.0+42.apk">App</a>', encoding="utf-8")
    (tmp_path / "familienhub-1.0.0+42.apk").write_bytes(b"PK\x03\x04apk")
    web = FastAPI()
    assert mount_downloads(web, str(tmp_path)) is True
    c = TestClient(web)
    assert "familienhub-1.0.0+42.apk" in c.get("/downloads/").text
    apk = c.get("/downloads/familienhub-1.0.0+42.apk")
    assert apk.content == b"PK\x03\x04apk"
    assert apk.headers["content-type"] == "application/vnd.android.package-archive"
