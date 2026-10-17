"""Smoke-Tests für die Kern-API."""


def test_health(client):
    data = client.get("/api/health").json()
    assert data["app"] == "Familienhub"
    assert data["status"] == "online"
    assert "nextcloud" in data["plugins"]
    assert set(data["features"]) == {"oidc", "push", "fcm", "webpush"}


def test_protected_requires_auth(client):
    for path in ("/api/today", "/api/modules", "/api/tasks", "/api/shopping", "/api/reminders"):
        assert client.get(path).status_code == 401, path


def test_removed_legacy_endpoints_are_gone(client, auth):
    """Altlasten aus Hermes (Issue #17) sind weg – insbesondere der offene HA-Dienstaufruf."""
    for method, path in [("post", "/api/smarthome/service"), ("get", "/api/dashboard"), ("post", "/api/ai/chat"),
                         ("get", "/api/finance/overview"), ("get", "/api/search?q=x"), ("get", "/api/connectors"),
                         ("post", "/api/notifications/subscribe")]:
        assert client.request(method, path, headers=auth).status_code == 404, path


def test_login_and_me(client, auth):
    me = client.get("/api/auth/me", headers=auth).json()
    assert me["username"] == "admin"
    assert me["role"] == "admin"


def test_reminder_crud(client, auth):
    created = client.post("/api/reminders", headers=auth, json={"title": "Testerinnerung", "priority": "important"})
    assert created.status_code == 200
    rid = created.json()["id"]
    assert any(r["id"] == rid for r in client.get("/api/reminders", headers=auth).json())
    done = client.patch(f"/api/reminders/{rid}", headers=auth, json={"completed": True})
    assert done.status_code == 200 and done.json()["completed"] is True


def test_vapid_key_moved_to_push(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "vapid_public_key", "PUB")
    monkeypatch.setattr(settings, "vapid_private_key", "PRIV")
    assert client.get("/api/push/vapid-public-key").json() == {"publicKey": "PUB"}
    monkeypatch.setattr(settings, "vapid_private_key", None)
    assert client.get("/api/push/vapid-public-key").status_code == 501
