"""Stille Aktualisierungs-Pushes für Widgets: nach Änderungen im Hub und auf Zuruf von Home Assistant."""

import asyncio

import pytest

from app.services import refresh as refresh_module


@pytest.fixture
def scheduled(monkeypatch):
    calls = []
    monkeypatch.setattr(refresh_module, "schedule_refresh", lambda scope: calls.append(scope))
    return calls


@pytest.fixture
def key(client, auth):
    r = client.post("/api/admin/service-keys", headers=auth, json={"name": "Home Assistant"})
    return {"Authorization": f"Bearer {r.json()['key']}"}


def test_changes_schedule_refresh_reads_do_not(client, auth, scheduled):
    client.get("/api/reminders", headers=auth)
    client.get("/api/today", headers=auth)
    assert scheduled == []
    r = client.post("/api/reminders", headers=auth, json={"title": "Müll"})
    assert r.status_code == 200
    assert scheduled == ["reminders"]


def test_failed_changes_do_not_schedule(client, auth, scheduled):
    client.patch("/api/reminders/999999", headers=auth, json={"title": "x"})  # 404
    client.post("/api/reminders", json={"title": "ohne Anmeldung"})  # 401
    assert scheduled == []


def test_unrelated_paths_do_not_schedule(client, auth, scheduled):
    client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    client.post("/api/admin/service-keys", headers=auth, json={"name": "x"})
    assert scheduled == []


def test_external_refresh_needs_service_key(client, auth, key, scheduled):
    assert client.post("/api/refresh", json={"scope": "shopping"}).status_code == 401
    assert client.post("/api/refresh", headers=auth, json={"scope": "shopping"}).status_code == 401
    r = client.post("/api/refresh", headers=key, json={"scope": "shopping"})
    assert r.status_code == 202 and scheduled == ["shopping"]
    assert client.post("/api/refresh", headers=key, json={"scope": "alles"}).status_code == 422


def test_refresh_is_coalesced_and_throttled(monkeypatch):
    """Viele Änderungen kurz hintereinander → ein Push; danach frühestens nach der Sperrzeit."""
    sent = []

    async def fake_send(scopes):
        sent.append(sorted(scopes))

    monkeypatch.setattr(refresh_module, "_send_refresh", fake_send)
    monkeypatch.setattr(refresh_module, "_enabled", lambda: True)
    monkeypatch.setattr(refresh_module, "DEBOUNCE", 0.05)
    monkeypatch.setattr(refresh_module, "MIN_INTERVAL", 0.3)
    refresh_module._reset()

    async def scenario():
        for scope in ("shopping", "tasks", "shopping"):
            refresh_module.schedule_refresh(scope)
        await asyncio.sleep(0.15)
        assert sent == [["shopping", "tasks"]]
        refresh_module.schedule_refresh("meals")
        await asyncio.sleep(0.1)
        assert len(sent) == 1  # Sperrzeit läuft noch
        await asyncio.sleep(0.35)
        assert sent == [["shopping", "tasks"], ["meals"]]

    asyncio.run(scenario())


def test_refresh_message_is_silent_data_only():
    msg = refresh_module.refresh_message("tok", ["shopping", "tasks"])
    assert "notification" not in msg
    assert msg["data"] == {"type": "refresh", "scope": "shopping,tasks"}
    assert msg["android"]["priority"] == "HIGH"
    assert msg["token"] == "tok"


def test_without_fcm_nothing_is_scheduled(monkeypatch):
    monkeypatch.setattr(refresh_module, "_enabled", lambda: False)
    refresh_module._reset()
    refresh_module.schedule_refresh("shopping")
    assert refresh_module._pending == set() and refresh_module._task is None
