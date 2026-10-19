"""Reusable template lists (#20): saved by adults, applied to the shopping list or the tasks."""

import httpx
import pytest
import respx

from app.config import settings
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User


def _login(client, role):
    name = f"tpl_{role}"
    with SessionLocal() as db:
        if not db.query(User).filter(User.username == name).first():
            db.add(User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"), role=role))
            db.commit()
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def hub_list(monkeypatch):
    monkeypatch.setattr(settings, "homeassistant_url", None)
    monkeypatch.setattr(settings, "homeassistant_token", None)


def _open(client, h):
    groups = client.get("/api/shopping", headers=h).json()["groups"]
    return sorted(i["summary"] for g in groups for i in g["items"] if i["status"] == "needs_action")


def _clear(client, h):
    for g in client.get("/api/shopping", headers=h).json()["groups"]:
        for i in g["items"]:
            client.delete(f"/api/shopping/{i['uid']}", headers=h)


def _make(client, h, name="Packliste", items=None):
    items = items if items is not None else [{"name": "Zahnbürste"}, {"name": "Sonnencreme", "note": "LSF 50"},
                                             {"name": "  ", "note": "x"}]
    r = client.post("/api/templates", headers=h, json={"name": name, "items": items})
    assert r.status_code == 201, r.text
    return r.json()


def test_crud_and_blank_items_dropped(client, auth):
    t = _make(client, auth)
    assert [i["name"] for i in t["items"]] == ["Zahnbürste", "Sonnencreme"] and t["item_count"] == 2
    r = client.put(f"/api/templates/{t['id']}", headers=auth,
                   json={"name": "Reise", "items": [{"name": "Pass", "note": "1x"}]})
    assert r.json()["name"] == "Reise" and r.json()["items"][0]["note"] == "1x"
    assert any(x["id"] == t["id"] for x in client.get("/api/templates", headers=auth).json()["items"])
    assert client.delete(f"/api/templates/{t['id']}", headers=auth).status_code == 204
    assert client.get(f"/api/templates/{t['id']}", headers=auth).status_code == 404
    assert client.post("/api/templates", headers=auth, json={"name": "  "}).status_code == 422


def test_roles(client, auth):
    t = _make(client, auth)
    for role in ("child", "guest"):
        h = _login(client, role)
        assert client.get("/api/templates", headers=h).status_code == 200
        assert client.post("/api/templates", headers=h, json={"name": "x"}).status_code == 403
        assert client.put(f"/api/templates/{t['id']}", headers=h, json={"name": "x"}).status_code == 403
        assert client.delete(f"/api/templates/{t['id']}", headers=h).status_code == 403
        assert client.post(f"/api/templates/{t['id']}/apply/tasks", headers=h, json={}).status_code == 403
        assert client.post("/api/templates/from-shopping", headers=h, json={"name": "x"}).status_code == 403
        # shopping may be added to by every role
        assert client.post(f"/api/templates/{t['id']}/apply/shopping", headers=h, json={}).status_code == 200
    partner = _login(client, "partner")
    assert client.put(f"/api/templates/{t['id']}", headers=partner, json={"name": "Von Partner"}).status_code == 200


def test_apply_to_shopping_skips_open_items_and_supports_subset(client, auth, hub_list):
    _clear(client, auth)
    client.post("/api/shopping", headers=auth, json={"item": "  zahnbürste "})
    t = _make(client, auth, items=[{"name": "Zahnbürste"}, {"name": "Sonnencreme", "note": "LSF 50"},
                                   {"name": "SONNENCREME"}, {"name": "Hut"}])
    r = client.post(f"/api/templates/{t['id']}/apply/shopping", headers=auth, json={}).json()
    assert (r["added"], r["skipped"]) == (2, 2)
    assert _open(client, auth) == ["Hut", "Sonnencreme (LSF 50)", "zahnbürste"]
    again = client.post(f"/api/templates/{t['id']}/apply/shopping", headers=auth, json={}).json()
    assert (again["added"], again["skipped"]) == (0, 4)

    _clear(client, auth)
    hut = next(i["id"] for i in t["items"] if i["name"] == "Hut")
    r = client.post(f"/api/templates/{t['id']}/apply/shopping", headers=auth, json={"item_ids": [hut]}).json()
    assert r["added"] == 1 and _open(client, auth) == ["Hut"]
    assert client.post(f"/api/templates/{t['id']}/apply/shopping", headers=auth,
                       json={"item_ids": [999999]}).status_code == 422


def test_template_from_shopping_list(client, auth, hub_list):
    _clear(client, auth)
    for item in ("Milch", "milch ", "Brot"):
        client.post("/api/shopping", headers=auth, json={"item": item})
    t = client.post("/api/templates/from-shopping", headers=auth, json={"name": "Wocheneinkauf"})
    assert t.status_code == 201
    assert [i["name"] for i in t.json()["items"]] == ["Milch", "Brot"]
    _clear(client, auth)
    assert client.post("/api/templates/from-shopping", headers=auth, json={"name": "Leer"}).status_code == 422


@respx.mock
def test_apply_to_shopping_through_home_assistant(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "homeassistant_url", "http://ha.test")
    monkeypatch.setattr(settings, "homeassistant_token", "tok")
    monkeypatch.setattr(settings, "ha_shopping_todo", "todo.einkauf_tpl")
    t = _make(client, auth, items=[{"name": "Milch", "note": "2 l"}, {"name": "Brot"}])
    respx.route(host="ha.test", path="/api/services/todo/get_items").mock(return_value=httpx.Response(
        200, json={"service_response": {"todo.einkauf_tpl": {"items": [
            {"uid": "1", "summary": "milch", "status": "needs_action"}]}}}))
    add = respx.route(host="ha.test", path="/api/services/todo/add_item").mock(return_value=httpx.Response(200, json=[]))
    r = client.post(f"/api/templates/{t['id']}/apply/shopping", headers=auth, json={}).json()
    assert (r["added"], r["skipped"]) == (1, 1)
    assert add.call_count == 1 and b"Brot" in add.calls[0].request.content


def test_apply_to_shopping_without_list_is_soft(client, auth, monkeypatch):
    from app.routers import shopping

    async def none():
        return None

    monkeypatch.setattr(shopping, "open_shopping_summaries", none)
    t = _make(client, auth)
    r = client.post(f"/api/templates/{t['id']}/apply/shopping", headers=auth, json={})
    assert r.status_code == 200 and r.json()["status"] == "unavailable" and r.json()["added"] == 0


def test_apply_to_tasks_creates_one_task_per_item(client, auth):
    t = _make(client, auth, items=[{"name": "Koffer holen"}, {"name": "Pässe prüfen", "note": "alle vier"}])
    keep = t["items"][1]["id"]
    r = client.post(f"/api/templates/{t['id']}/apply/tasks", headers=auth, json={"item_ids": [keep]})
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 1 and r.json()["failed"] == 0
    r = client.post(f"/api/templates/{t['id']}/apply/tasks", headers=auth, json={"list": "family"}).json()
    assert r["created"] == 2
    titles = {x["title"]: x for x in client.get("/api/tasks", params={"provider": "all", "view": "all"},
                                                 headers=auth).json()["items"]}
    assert "Pässe prüfen" in titles and "Koffer holen" in titles
    assert client.post(f"/api/templates/{t['id']}/apply/tasks", headers=auth, json={"list": "x"}).status_code == 422
