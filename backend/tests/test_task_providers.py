"""Dritter Anbieter durch dieselbe Plugin-/Routergrenze, ohne Fachsystemzugriffe."""
from app.plugins.base import Plugin
from app.plugins.registry import plugin_registry
from app.core.security import create_access_token
from tests.test_household import _household_user


class ExampleConnector:
    is_configured = True

    def __init__(self, user_id):
        self.account_ref = str(user_id)
        self.user_id = user_id

    async def get_tasks(self, **kwargs):
        return {"status": "ok", "error": None, "items": [{"uid": "same-id", "title": "Dritter Anbieter", "assignee": self.user_id}]}

    async def create_task(self, **kwargs):
        return {"uid": "same-id", "title": kwargs["title"]}

    async def update_task(self, uid, **kwargs):
        return {"uid": uid, "title": kwargs["title"]}

    async def complete_task(self, uid):
        return {"uid": uid, "done": True}

    async def delete_task(self, uid):
        return True


class ExamplePlugin(Plugin):
    def task_connector(self, user_id, db):
        return ExampleConnector(user_id)


def test_third_provider_uses_explicit_current_account(client, monkeypatch):
    user = _household_user("provider-example")
    headers = {"Authorization": f"Bearer {create_access_token({'sub': user.username})}"}
    monkeypatch.setitem(plugin_registry._plugins, "example", ExamplePlugin(
        id="example", name="Beispiel", capabilities=frozenset({"tasks"})))
    query = f"provider=example&account={user.id}"
    result = client.get(f"/api/tasks?{query}", headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["items"][0]["provider"] == "example"
    assert result.json()["items"][0]["account"] == str(user.id)
    for method, suffix, payload in [("post", "", {"title": "Neu"}),
                                     ("patch", "/same-id", {"title": "Editiert"}),
                                     ("post", "/same-id/complete", None),
                                     ("delete", "/same-id", None)]:
        response = client.request(method, f"/api/tasks{suffix}?{query}", headers=headers, json=payload)
        assert response.status_code in (200, 201, 204), response.text
        response = client.request(method, f"/api/tasks{suffix}?provider=example&account={user.id + 1}", headers=headers, json=payload)
        assert response.status_code == 403, response.text
    from app.config import settings
    monkeypatch.setattr(settings, "plugins_disabled", "example")
    assert client.post(f"/api/tasks?{query}", headers=headers, json={"title": "Nein"}).status_code == 409


def test_plugin_factory_failure_does_not_block_other_provider_or_today(client, monkeypatch):
    user = _household_user("provider-isolation")
    headers = {"Authorization": f"Bearer {create_access_token({'sub': user.username})}"}
    good = ExamplePlugin(id="example", name="Beispiel", capabilities=frozenset({"tasks"}))
    bad = ExamplePlugin(id="broken", name="Kaputt", capabilities=frozenset({"tasks"}))
    def fail(*args):
        raise RuntimeError("provider setup failed")
    monkeypatch.setattr(bad, "task_connector", fail)
    monkeypatch.setitem(plugin_registry._plugins, "example", good)
    monkeypatch.setitem(plugin_registry._plugins, "broken", bad)
    providers = client.get("/api/tasks/providers", headers=headers)
    assert providers.status_code == 200, providers.text
    assert any(p["id"] == "example" for p in providers.json()["items"])
    aggregate = client.get("/api/tasks?provider=all", headers=headers)
    assert aggregate.status_code == 200, aggregate.text
    assert any(t["provider"] == "example" for t in aggregate.json()["items"])
    assert aggregate.json()["providers"]["broken"]["status"] == "unavailable"
    assert any(t["provider"] == "example" for t in client.get("/api/today", headers=headers).json()["tasks"]["items"])


def test_nextcloud_context_changes_with_personal_server_and_rejects_old_writes(client):
    from app.core.database import SessionLocal
    from app.core.crypto import encrypt
    from app.models.caldav import CalDAVAccount
    user = _household_user("nextcloud-server-scope")
    headers = {"Authorization": f"Bearer {create_access_token({'sub': user.username})}"}
    with SessionLocal() as db:
        account = CalDAVAccount(user_id=user.id, url="https://caldav.example/old", username="own-account", password_enc=encrypt("test-only"))
        db.add(account); db.commit()
    old = next(p["account"] for p in client.get("/api/tasks/providers", headers=headers).json()["items"] if p["id"] == "nextcloud")
    with SessionLocal() as db:
        db.query(CalDAVAccount).filter_by(user_id=user.id).update({"url": "https://caldav.example/new"}); db.commit()
    response = client.post(f"/api/tasks?provider=nextcloud&account={old}", headers=headers, json={"title": "Nicht an neuen Server senden"})
    assert response.status_code == 403, response.text
    new = next(p["account"] for p in client.get("/api/tasks/providers", headers=headers).json()["items"] if p["id"] == "nextcloud")
    assert new != old
