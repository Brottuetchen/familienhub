"""SHOPPING_RECIPE_INGREDIENTS: merge Cookidoo/Mealie ingredients onto our list (default) or leave them in the source."""

from datetime import date
from types import SimpleNamespace as NS

import httpx
import pytest
import respx

from app.config import settings
from app.services import cookidoo as cookidoo_module
from app.services import config_store

M = "http://mealie.test:9000"
TODAY = date.today().isoformat()


class FakeCookidoo:
    def __init__(self):
        self.shopping = []

    async def login(self):
        pass

    async def get_recipes_in_calendar_week(self, day):
        r = NS(id="c9", name="Wildlasagne", total_time="600", thumbnail=None, image=None, url="u")
        return [NS(id=TODAY, title=TODAY, recipes=[r], customer_recipe_ids=[])]

    async def get_recipe_details(self, id):
        return NS(id=id, name="Wildlasagne", image=None, thumbnail=None, url="u", total_time=600, active_time=0,
                  serving_size=2, difficulty="easy",
                  ingredients=[NS(id="i1", name="Wildhack", description="500 g"),
                               NS(id="i2", name="Passata", description="2 Dosen")])

    async def add_ingredient_items_for_recipes(self, recipe_ids):
        self.shopping.extend(recipe_ids)
        return [NS(id="x", name="Zutat")]


@pytest.fixture
def cookidoo(monkeypatch):
    fake = FakeCookidoo()

    async def factory(cfg):
        return fake

    monkeypatch.setenv("COOKIDOO_EMAIL", "koch@test.de")
    monkeypatch.setenv("COOKIDOO_PASSWORD", "geheim")
    monkeypatch.setattr(cookidoo_module.cookidoo_service, "_factory", factory)
    cookidoo_module.cookidoo_service.reset()
    yield fake
    cookidoo_module.cookidoo_service.reset()


@pytest.fixture
def mealie(monkeypatch):
    from app.services.mealie import mealie_service

    monkeypatch.setitem(config_store._extra, "MEALIE_URL", M)
    monkeypatch.setitem(config_store._extra, "MEALIE_TOKEN", "t")
    monkeypatch.setattr(settings, "homeassistant_url", None)
    monkeypatch.setattr(settings, "homeassistant_token", None)
    mealie_service._group_slug = None
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        http.get(f"{M}/api/groups/self").mock(return_value=httpx.Response(200, json={"slug": "home"}))
        http.get(f"{M}/api/households/shopping/lists").mock(
            return_value=httpx.Response(200, json={"items": [{"id": "L1", "name": "Einkauf"}]}))
        http.get(f"{M}/api/households/mealplans").mock(return_value=httpx.Response(200, json={"items": [
            {"id": 1, "date": TODAY, "entryType": "dinner", "recipeId": "m9",
             "recipe": {"id": "m9", "name": "Wildcurry", "slug": "s"}}]}))
        http.get(f"{M}/api/recipes/m9").mock(return_value=httpx.Response(200, json={
            "id": "m9", "name": "Wildcurry", "recipeIngredient": [{"display": "1 Dose Passata"}, {"display": "300 g Wildhack"}]}))
        http.native = http.post(f"{M}/api/households/shopping/lists/L1/recipe/m9").mock(
            return_value=httpx.Response(200, json={}))
        yield http


@pytest.fixture(autouse=True)
def empty_hub_list():
    """The test database is shared: start every test here with an empty hub shopping list (no-doubling rule)."""
    from app.core.database import SessionLocal
    from app.models.hub import HubShoppingItem, ShoppingItemRecipes

    with SessionLocal() as db:
        db.query(ShoppingItemRecipes).delete()
        db.query(HubShoppingItem).delete()
        db.commit()
    yield


def _hub(client, h):
    groups = client.get("/api/shopping", headers=h).json()["groups"]
    return {i["summary"]: i for g in groups for i in g["items"] if i["status"] == "needs_action"}


def _mode(monkeypatch, mode):
    if mode:
        monkeypatch.setitem(config_store._extra, "SHOPPING_RECIPE_INGREDIENTS", mode)


@pytest.mark.parametrize("mode", [None, "merge"])
def test_merge_mode_week_button_merges_sources_onto_our_list(client, auth, cookidoo, mealie, monkeypatch, mode):
    _mode(monkeypatch, mode)
    r = client.post("/api/meals/shopping-list?days=1", headers=auth).json()
    assert all(s["status"] == "ok" for s in r["sources"])
    assert cookidoo.shopping == [] and mealie.native.call_count == 0
    items = _hub(client, auth)
    assert items["800 g Wildhack"]["recipes"] == ["Wildlasagne", "Wildcurry"]
    assert items["3 Dosen Passata"]["recipes"] == ["Wildlasagne", "Wildcurry"]
    again = client.post("/api/meals/shopping-list?days=1", headers=auth).json()  # no doubling
    assert "800 g Wildhack" in _hub(client, auth) and "1600 g Wildhack" not in _hub(client, auth)
    assert sum(s["added"] for s in again["sources"]) == 0


def test_source_mode_week_button_leaves_ingredients_in_the_sources(client, auth, cookidoo, mealie, monkeypatch):
    _mode(monkeypatch, "source")
    r = client.post("/api/meals/shopping-list?days=1", headers=auth).json()
    assert all(s["status"] == "ok" for s in r["sources"])
    assert cookidoo.shopping == ["c9"] and mealie.native.call_count == 1
    assert not any("Wildhack" in s for s in _hub(client, auth))


def test_source_mode_hub_recipes_still_merge_on_our_list(client, auth, cookidoo, mealie, monkeypatch):
    _mode(monkeypatch, "source")
    rid = client.post("/api/recipes", headers=auth, json={"title": "Hubsuppe", "ingredients": ["1 Hubrübe"]}).json()["id"]
    client.post("/api/recipes/%d/shopping" % rid, headers=auth)
    rid2 = client.post("/api/recipes", headers=auth, json={"title": "Hubeintopf", "ingredients": ["2 Hubrüben"]}).json()["id"]
    client.post("/api/recipes/%d/shopping" % rid2, headers=auth)
    assert _hub(client, auth)["3 Hubrüben"]["recipes"] == ["Hubsuppe", "Hubeintopf"]


def test_per_recipe_action_follows_the_mode(client, auth, cookidoo, mealie, monkeypatch):
    _mode(monkeypatch, "merge")
    assert client.post("/api/recipe-sources/cookidoo/shopping", headers=auth, json={"recipe_ids": ["c9"]}).json()["added"] == 2
    assert cookidoo.shopping == [] and "500 g Wildhack" in _hub(client, auth)
    assert client.post("/api/recipe-sources/cookidoo/shopping", headers=auth, json={"recipe_ids": ["c9"]}).json()["added"] == 0
    _mode(monkeypatch, "source")
    client.post("/api/recipe-sources/cookidoo/shopping", headers=auth, json={"recipe_ids": ["c9"]})
    client.post("/api/recipe-sources/mealie/shopping", headers=auth, json={"recipe_ids": ["m9"]})
    assert cookidoo.shopping == ["c9"] and mealie.native.call_count == 1


def test_admin_can_choose_the_mode(client, auth, monkeypatch):
    def mode():
        areas = client.get("/api/admin/sources", headers=auth).json()["areas"]
        return next(a for a in areas if a["area"] == "shopping")["recipe_ingredients"]

    monkeypatch.setitem(config_store._extra, "SHOPPING_RECIPE_INGREDIENTS", "")
    assert mode() == "merge"
    assert client.put("/api/admin/recipe-ingredients", headers=auth, json={"mode": "source"}).status_code == 200
    assert mode() == "source"
    assert client.put("/api/admin/recipe-ingredients", headers=auth, json={"mode": "bogus"}).status_code == 422
    assert client.put("/api/admin/recipe-ingredients", headers=auth, json={"mode": "merge"}).status_code == 200
    assert mode() == "merge"
