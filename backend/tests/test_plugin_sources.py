"""External plugins as data sources: shopping list and recipes (fake plugins, no real service)."""

import asyncio
from datetime import date, timedelta

import pytest

from app.config import settings
from app.core.database import SessionLocal
from app.models.recipe import MealPlanEntry
from app.plugins.base import Plugin
from app.plugins.registry import plugin_registry
from app.plugins.sources import ShoppingConnector
from app.services import config_store

TODAY = date.today().isoformat()


class FakeList(ShoppingConnector):
    """The simulated external system: an in-memory list."""

    def __init__(self):
        self.items = {}
        self.seq = 0
        self.broken = False
        self.hang = False

    def _check(self):
        if self.broken:
            raise RuntimeError("secret-token leaked in message")

    async def list_items(self):
        self._check()
        if self.hang:
            await asyncio.sleep(30)
        return [{"uid": uid, **row} for uid, row in self.items.items()]

    async def add(self, summary, user_id=None, description=None):
        self._check()
        self.seq += 1
        self.items[f"i{self.seq}"] = {"summary": summary, "status": "needs_action", "description": description or "",
                                      "amount": "2" if "Milch" in summary else None}
        return True

    async def set_done(self, uid, done):
        self._check()
        if uid not in self.items:
            return False
        self.items[uid]["status"] = "completed" if done else "needs_action"
        return True

    async def delete(self, uid):
        self._check()
        return self.items.pop(uid, None) is not None


class ShopPlugin(Plugin):
    def __init__(self, connector):
        super().__init__(id="fakeshop", name="Fake Shop", capabilities=frozenset({"shopping"}))
        self.connector = connector

    def shopping_connector(self, db):
        return self.connector


@pytest.fixture
def shop(monkeypatch):
    connector = FakeList()
    plugin = ShopPlugin(connector)
    plugin_registry.register(plugin)
    monkeypatch.setitem(config_store._extra, "SHOPPING_SOURCE", "fakeshop")
    yield connector
    plugin_registry.unregister("fakeshop")


def _open(client, auth):
    body = client.get("/api/shopping", headers=auth).json()
    return body, [i for g in body["groups"] for i in g["items"] if i["status"] == "needs_action"]


def test_plugin_is_listed_and_selectable_as_shopping_source(client, auth, monkeypatch):
    monkeypatch.setitem(config_store._extra, "SHOPPING_SOURCE", "")
    plugin_registry.register(ShopPlugin(FakeList()))
    try:
        areas = {a["area"]: a for a in client.get("/api/admin/sources", headers=auth).json()["areas"]}
        assert "fakeshop" in {s["id"] for s in areas["shopping"]["sources"]}
        r = client.put("/api/admin/sources", headers=auth, json={"area": "shopping", "selected": ["fakeshop"]})
        assert r.status_code == 200, r.text
        assert config_store.get_override("SHOPPING_SOURCE") == "fakeshop"
    finally:
        plugin_registry.unregister("fakeshop")
        client.put("/api/admin/sources", headers=auth, json={"area": "shopping", "selected": []})


def test_shopping_list_end_to_end(client, auth, shop):
    assert client.post("/api/shopping", headers=auth, json={"item": "Milch"}).status_code == 200
    assert client.post("/api/shopping", headers=auth, json={"item": "Brot"}).status_code == 200
    body, items = _open(client, auth)
    assert body["status"] == "ok" and body["groups"][0]["entity"] == "fakeshop"
    milk = next(i for i in items if i["summary"] == "Milch")
    assert set(milk) >= {"uid", "summary", "status", "amount", "recipes"} and milk["amount"] == "2" and milk["description"] == "2"
    assert [i["summary"] for i in items] == ["Milch", "Brot"]
    assert shop.items[milk["uid"]]["summary"] == "Milch"  # it really went to the plugin, not the hub list

    assert client.patch(f"/api/shopping/{milk['uid']}", headers=auth, json={"done": True}).status_code == 200
    assert [i["summary"] for i in _open(client, auth)[1]] == ["Brot"]
    assert client.get("/api/shopping/recent", headers=auth).json() == ["Milch"]
    assert client.patch(f"/api/shopping/{milk['uid']}", headers=auth, json={"done": False}).status_code == 200
    assert len(_open(client, auth)[1]) == 2
    assert client.delete(f"/api/shopping/{milk['uid']}", headers=auth).status_code == 200
    assert client.delete(f"/api/shopping/{milk['uid']}", headers=auth).status_code == 404
    assert client.patch("/api/shopping/nope", headers=auth, json={"done": True}).status_code == 404
    # the hub's own list stays untouched
    from app.models.hub import HubShoppingItem

    with SessionLocal() as db:
        assert db.query(HubShoppingItem).filter(HubShoppingItem.summary.in_(["Milch", "Brot"])).count() == 0


def test_template_recipe_ingredients_and_voice_use_the_plugin(client, auth, shop):
    t = client.post("/api/templates", headers=auth, json={"name": "Camping", "items": [{"name": "Zelt"}, {"name": "Seil"}]}).json()
    r = client.post(f"/api/templates/{t['id']}/apply/shopping", headers=auth, json={}).json()
    assert r["status"] == "ok" and r["added"] == 2
    # applying again adds nothing: the open entries are read from the plugin
    assert client.post(f"/api/templates/{t['id']}/apply/shopping", headers=auth, json={}).json()["skipped"] == 2

    recipe = client.post("/api/recipes", headers=auth, json={"title": "Pfannkuchen", "ingredients": ["200 g Mehl", "3 Eier"]}).json()
    added = client.post(f"/api/recipes/{recipe['id']}/shopping", headers=auth).json()["added"]
    assert added == 2

    key = client.post("/api/auth/api-tokens", headers=auth, json={"name": "V", "scopes": ["voice"]}).json()["token"]
    v = client.post("/api/voice/shopping/items", headers={"Authorization": f"Bearer {key}"}, json={"items": "milk and butter"})
    assert v.status_code == 200 and v.json()["ok"] is True
    summaries = {i["summary"] for i in shop.items.values()}
    assert {"Zelt", "Seil", "Milk", "Butter"} <= summaries and any("Mehl" in s for s in summaries)
    spoken = client.get("/api/voice/shopping", headers={"Authorization": f"Bearer {key}"}).json()
    assert "Milk" in spoken["items"]


def test_broken_plugin_fails_softly(client, auth, shop):
    shop.broken = True
    body = client.get("/api/shopping", headers=auth).json()
    assert body["status"] == "unavailable" and body["groups"] == []
    assert "secret-token" not in str(body)  # exception text of the plugin never reaches the app
    assert client.post("/api/shopping", headers=auth, json={"item": "Milch"}).status_code == 502
    assert client.get("/api/shopping/recent", headers=auth).json() == []
    today = client.get("/api/today", headers=auth)
    assert today.status_code == 200 and today.json()["shopping_open"] == 0


def test_hanging_plugin_times_out(client, auth, shop, monkeypatch):
    from app.plugins import sources

    monkeypatch.setattr(sources, "PLUGIN_TIMEOUT", 0.2)
    shop.hang = True
    body = client.get("/api/shopping", headers=auth).json()
    assert body["status"] == "unavailable"


def test_plugin_without_connector_falls_back_to_the_hub_list(client, auth, shop, monkeypatch):
    monkeypatch.setattr(settings, "homeassistant_url", None)
    monkeypatch.setattr(settings, "homeassistant_token", None)
    plugin_registry.get("fakeshop").connector = None
    assert client.post("/api/shopping", headers=auth, json={"item": "Fallback-Tee"}).status_code == 200
    groups = client.get("/api/shopping", headers=auth).json()["groups"]
    assert any(i["summary"] == "Fallback-Tee" for g in groups for i in g["items"])
    assert shop.items == {}


def test_merge_without_rename_lists_lines_separately(client, auth, shop):
    from app.routers.shopping import add_recipe_ingredients

    asyncio.run(add_recipe_ingredients([("A", ["200 g Zwiebeln"])], None))
    asyncio.run(add_recipe_ingredients([("B", ["1 Zwiebel"])], None))
    assert sorted(i["summary"] for i in shop.items.values()) == ["1 Zwiebel", "200 g Zwiebeln"]


# --- recipes ------------------------------------------------------------------------------------------------


class RecipePlugin(Plugin):
    def __init__(self):
        super().__init__(id="fakecook", name="Fake Cook", capabilities=frozenset({"meal_planning"}))
        self.fail = False
        self.sent = []

    async def recipe_search(self, query, limit):
        if self.fail:
            raise RuntimeError("down")
        return [{"id": 7, "name": f"{query} Auflauf", "thumbnail": "/api/plugins/fakecook/img/7", "url": "https://x.test/7",
                 "minutes": 40}, {"name": "no id"}, "garbage"]

    async def recipe(self, recipe_id):
        if self.fail or recipe_id != "7":
            raise RuntimeError("down")
        return {"id": "7", "name": "Kartoffel Auflauf", "image": "/api/plugins/fakecook/img/7", "url": "https://x.test/7",
                "servings": 4, "minutes": 40, "ingredients": ["500 g Kartoffeln", "200 ml Sahne"], "steps": ["Schneiden", "Backen"]}


class ListRecipePlugin(RecipePlugin):
    async def recipe_to_shopping(self, recipe_ids, user_id=None):
        self.sent.append(list(recipe_ids))
        return len(recipe_ids)


@pytest.fixture
def cook(monkeypatch):
    plugin = RecipePlugin()
    plugin_registry.register(plugin)
    monkeypatch.setitem(config_store._extra, "SHOPPING_SOURCE", "hub_shopping")
    yield plugin
    plugin_registry.unregister("fakecook")


def test_recipe_source_listed_search_and_details(client, auth, cook):
    assert {"id": "fakecook", "name": "Fake Cook"} in client.get("/api/recipe-sources", headers=auth).json()
    r = client.get("/api/recipe-sources/fakecook/search", params={"q": "Kartoffel"}, headers=auth).json()
    assert r["status"] == "ok" and r["total"] == 1
    assert r["items"][0] == {"id": "7", "name": "Kartoffel Auflauf", "image": "/api/plugins/fakecook/img/7",
                             "thumbnail": "/api/plugins/fakecook/img/7", "url": "https://x.test/7", "minutes": 40}
    d = client.get("/api/recipe-sources/fakecook/recipes/7", headers=auth).json()
    assert d["status"] == "ok" and d["title"] == "Kartoffel Auflauf" and d["servings"] == 4
    assert d["ingredients"] == ["500 g Kartoffeln", "200 ml Sahne"] and d["steps"] == ["Schneiden", "Backen"]
    assert client.get("/api/recipe-sources/unknown/search", params={"q": "abc"}, headers=auth).status_code == 409


def test_recipe_source_fails_softly(client, auth, cook):
    cook.fail = True
    r = client.get("/api/recipe-sources/fakecook/search", params={"q": "Kartoffel"}, headers=auth).json()
    assert r["status"] == "unavailable" and r["items"] == []
    assert "down" not in r["error"]
    d = client.get("/api/recipe-sources/fakecook/recipes/9", headers=auth).json()
    assert d["status"] == "unavailable"
    assert client.post("/api/recipe-sources/fakecook/plan", headers=auth, json={"date": TODAY, "recipe_id": "7"}).status_code == 503


def test_plan_shows_in_the_week_and_can_be_removed(client, auth, cook):
    assert client.post("/api/recipe-sources/fakecook/plan", headers=auth, json={"date": TODAY, "recipe_id": "7"}).status_code == 200
    client.post("/api/recipe-sources/fakecook/plan", headers=auth, json={"date": TODAY, "recipe_id": "7"})  # twice: one entry
    days = client.get("/api/meals", headers=auth).json()["days"]
    entries = [e for d in days if d["date"] == TODAY for e in d["entries"] if e["source"] == "fakecook"]
    assert len(entries) == 1
    assert entries[0]["recipe_id"] == "7" and entries[0]["title"] == "Kartoffel Auflauf"
    assert entries[0]["source_name"] == "Fake Cook" and entries[0]["minutes"] == 40
    assert entries[0]["image"] == "/api/plugins/fakecook/img/7"
    plan = client.get("/api/meals/plan", headers=auth).json()["days"]
    assert any(e["source"] == "fakecook" for d in plan for e in d["entries"])
    assert client.delete(f"/api/recipe-sources/fakecook/plan/{TODAY}/7", headers=auth).status_code == 200
    days = client.get("/api/meals", headers=auth).json()["days"]
    assert not [e for d in days for e in d["entries"] if e["source"] == "fakecook"]


def test_ingredients_go_to_the_hub_list_without_a_plugin_list(client, auth, cook):
    r = client.post("/api/recipe-sources/fakecook/shopping", headers=auth, json={"recipe_ids": ["7"]})
    assert r.status_code == 200 and r.json()["added"] == 2
    groups = client.get("/api/shopping", headers=auth).json()["groups"]
    texts = [i["summary"] for g in groups for i in g["items"]]
    assert "500 g Kartoffeln" in texts and "200 ml Sahne" in texts
    for g in groups:
        for i in g["items"]:
            client.delete(f"/api/shopping/{i['uid']}", headers=auth)


def test_recipe_to_shopping_hook_wins(client, auth, monkeypatch):
    plugin = ListRecipePlugin()
    plugin_registry.register(plugin)
    try:
        r = client.post("/api/recipe-sources/fakecook/shopping", headers=auth, json={"recipe_ids": ["7"]})
        assert r.json()["added"] == 1 and plugin.sent == [["7"]]
    finally:
        plugin_registry.unregister("fakecook")


def test_week_shopping_list_includes_planned_plugin_recipes(client, auth, cook):
    day = (date.today() + timedelta(days=1)).isoformat()
    client.post("/api/recipe-sources/fakecook/plan", headers=auth, json={"date": day, "recipe_id": "7"})
    r = client.post("/api/meals/shopping-list", headers=auth).json()
    assert any(s["source"] == "fakecook" and s["status"] == "ok" and s["added"] == 2 for s in r["sources"]), r
    client.delete(f"/api/recipe-sources/fakecook/plan/{day}/7", headers=auth)
    groups = client.get("/api/shopping", headers=auth).json()["groups"]
    for g in groups:
        for i in g["items"]:
            client.delete(f"/api/shopping/{i['uid']}", headers=auth)


def test_entries_of_a_removed_plugin_are_hidden(client, auth, cook):
    client.post("/api/recipe-sources/fakecook/plan", headers=auth, json={"date": TODAY, "recipe_id": "7"})
    plugin_registry.unregister("fakecook")
    try:
        days = client.get("/api/meals", headers=auth).json()["days"]
        assert not [e for d in days for e in d["entries"] if e["source"] == "fakecook"]
    finally:
        with SessionLocal() as db:
            db.query(MealPlanEntry).filter(MealPlanEntry.source == "fakecook").delete()
            db.commit()
        plugin_registry.register(cook)
