"""Merged recipe ingredients on the shopping list (#70) and their recipe references (#69): hub list and Home Assistant."""

from datetime import date

import httpx
import pytest
import respx

from app.config import settings

TODAY = date.today().isoformat()


def _items(client, h, key="manual"):
    groups = client.get("/api/shopping", headers=h).json()["groups"]
    return [i for g in groups if g["key"] == key for i in g["items"] if i["status"] == "needs_action"]


def _recipe(client, h, title, lines):
    return client.post("/api/recipes", headers=h, json={"title": title, "ingredients": lines}).json()["id"]


@pytest.fixture
def hub_list(monkeypatch):
    monkeypatch.setattr(settings, "homeassistant_url", None)
    monkeypatch.setattr(settings, "homeassistant_token", None)


def test_two_recipes_merge_on_the_hub_list(client, auth, hub_list):
    a = _recipe(client, auth, "Rindergulasch", ["300 g Schalotten", "2 Lorbeerblätter", "1 EL Paprikapulver"])
    b = _recipe(client, auth, "Zwiebelkuchen", ["2 Schalotte", "500 g Schalotten", "1 TL Paprikapulver"])
    assert client.post(f"/api/recipes/{a}/shopping", headers=auth).json()["added"] == 3
    assert client.post(f"/api/recipes/{b}/shopping", headers=auth).json()["added"] == 3
    items = {i["summary"]: i for i in _items(client, auth)}
    shallots = items["2 Schalotten + 800 g"]
    assert shallots["recipes"] == ["Rindergulasch", "Zwiebelkuchen"]
    assert items["1 EL Paprikapulver + 1 TL"]["recipes"] == ["Rindergulasch", "Zwiebelkuchen"]
    assert items["2 Lorbeerblätter"]["recipes"] == ["Rindergulasch"]
    assert "300 g Schalotten" not in items


def test_pressing_twice_does_not_double_amounts(client, auth, hub_list):
    rid = _recipe(client, auth, "Kürbissuppe", ["400 g Hokkaido", "1 Stange Sellerie"])
    client.post(f"/api/recipes/{rid}/shopping", headers=auth)
    again = client.post(f"/api/recipes/{rid}/shopping", headers=auth).json()
    assert again["added"] == 0
    names = [i["summary"] for i in _items(client, auth)]
    assert names.count("400 g Hokkaido") == 1 and names.count("1 Stange Sellerie") == 1


def test_merges_into_an_item_added_by_hand(client, auth, hub_list):
    client.post("/api/shopping", headers=auth, json={"item": "1 kg Süßkartoffeln"})
    rid = _recipe(client, auth, "Ofengemüse", ["500 g Süßkartoffeln"])
    client.post(f"/api/recipes/{rid}/shopping", headers=auth)
    items = {i["summary"]: i for i in _items(client, auth)}
    assert items["1½ kg Süßkartoffeln"]["recipes"] == ["Ofengemüse"]
    assert "1 kg Süßkartoffeln" not in items


def test_manual_item_has_no_recipes(client, auth, hub_list):
    client.post("/api/shopping", headers=auth, json={"item": "Klebeband"})
    assert next(i for i in _items(client, auth) if i["summary"] == "Klebeband")["recipes"] == []


def test_week_button_merges_across_recipes(client, auth, hub_list):
    a = _recipe(client, auth, "Wochen-Curry", ["2 Pastinaken", "1 Dose Kichererbsen"])
    b = _recipe(client, auth, "Wochen-Eintopf", ["1 Pastinake", "2 Dosen Kichererbsen"])
    for rid in (a, b):
        client.post("/api/meals/plan", headers=auth, json={"date": TODAY, "recipe_id": rid})
    r = client.post("/api/meals/shopping-list?days=1", headers=auth).json()
    assert r["added"] >= 4
    items = {i["summary"]: i for i in _items(client, auth)}
    assert items["3 Pastinaken"]["recipes"] == ["Wochen-Curry", "Wochen-Eintopf"] or \
        items["3 Pastinaken"]["recipes"] == ["Wochen-Eintopf", "Wochen-Curry"]
    assert "3 Dosen Kichererbsen" in items


# --- Home Assistant -----------------------------------------------------------------------------------------------


@pytest.fixture
def mock_ha(monkeypatch):
    monkeypatch.setattr(settings, "homeassistant_url", "http://ha.test")
    monkeypatch.setattr(settings, "homeassistant_token", "test-token")
    monkeypatch.setattr(settings, "ha_shopping_todo", "todo.einkauf_merge")
    monkeypatch.setattr(settings, "ha_recipe_shopping_todo", "todo.rezepte_merge")


def _ha_items(entity, items):
    return httpx.Response(200, json={"service_response": {entity: {"items": items}}})


def _body(call):
    import json

    return json.loads(call.request.content)


@respx.mock
def test_home_assistant_merge_renames_and_remembers_recipes(client, auth, mock_ha):
    open_items = [{"uid": "u1", "summary": "1 Fenchel", "status": "needs_action"},
                  {"uid": "u2", "summary": "Hefe", "status": "needs_action"}]

    def get_items(req):
        import json

        entity = json.loads(req.content)["entity_id"]
        return _ha_items(entity, open_items if entity == "todo.einkauf_merge" else [])

    respx.route(host="ha.test", path="/api/services/todo/get_items").mock(side_effect=get_items)
    add = respx.route(host="ha.test", path="/api/services/todo/add_item").mock(return_value=httpx.Response(200, json=[]))
    upd = respx.route(host="ha.test", path="/api/services/todo/update_item").mock(return_value=httpx.Response(200, json=[]))
    rid = _recipe(client, auth, "Fenchelsalat", ["2 Fenchel", "100 g Parmesan"])

    assert client.post(f"/api/recipes/{rid}/shopping", headers=auth).json()["added"] == 2
    assert upd.call_count == 1 and _body(upd.calls.last) == {
        "entity_id": "todo.einkauf_merge", "item": "u1", "rename": "3 Fenchel"}
    assert add.call_count == 1 and _body(add.calls.last)["item"] == "100 g Parmesan"

    # HA now reports the merged and the new entry: both carry the recipe
    open_items[:] = [{"uid": "u1", "summary": "3 Fenchel", "status": "needs_action"},
                     {"uid": "u2", "summary": "Hefe", "status": "needs_action"},
                     {"uid": "u3", "summary": "100 g Parmesan", "status": "needs_action"}]
    groups = {g["key"]: g for g in client.get("/api/shopping", headers=auth).json()["groups"]}
    by = {i["summary"]: i for i in groups["manual"]["items"]}
    assert by["3 Fenchel"]["recipes"] == ["Fenchelsalat"] and by["100 g Parmesan"]["recipes"] == ["Fenchelsalat"]
    assert by["Hefe"]["recipes"] == [] and groups["recipes"]["items"] == []


@respx.mock
def test_home_assistant_rename_failure_adds_the_line_separately(client, auth, mock_ha):
    respx.route(host="ha.test", path="/api/services/todo/get_items").mock(side_effect=lambda req: _ha_items(
        "todo.einkauf_merge", [{"uid": "u1", "summary": "1 Radieschen", "status": "needs_action"}]))
    add = respx.route(host="ha.test", path="/api/services/todo/add_item").mock(return_value=httpx.Response(200, json=[]))
    respx.route(host="ha.test", path="/api/services/todo/update_item").mock(return_value=httpx.Response(500))
    rid = _recipe(client, auth, "Radieschensalat", ["2 Radieschen"])
    assert client.post(f"/api/recipes/{rid}/shopping", headers=auth).json()["added"] == 1
    assert add.call_count == 1 and _body(add.calls.last)["item"] == "2 Radieschen"


@respx.mock
def test_home_assistant_unreadable_list_still_adds(client, auth, mock_ha):
    respx.route(host="ha.test", path="/api/services/todo/get_items").mock(return_value=httpx.Response(500))
    add = respx.route(host="ha.test", path="/api/services/todo/add_item").mock(return_value=httpx.Response(200, json=[]))
    rid = _recipe(client, auth, "Rettichsalat", ["1 Rettich", "1 Rettich"])
    assert client.post(f"/api/recipes/{rid}/shopping", headers=auth).json()["added"] == 2
    assert add.call_count == 1 and _body(add.calls.last)["item"] == "2 Rettich"


def test_migration_creates_recipe_table(tmp_path, monkeypatch):
    from alembic import command
    from sqlalchemy import create_engine, inspect

    from app.core.database import _alembic_config

    url = f"sqlite:///{tmp_path}/m.db"
    monkeypatch.setattr(settings, "database_url", url)
    command.upgrade(_alembic_config(), "head")
    assert "shopping_item_recipes" in inspect(create_engine(url)).get_table_names()
