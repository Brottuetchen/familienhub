"""Week button: ingredients of all planned recipes (hub, Cookidoo, Mealie) in one call, per-source summary."""

from datetime import date
from types import SimpleNamespace as NS

import httpx
import pytest
import respx

from app.services import cookidoo as cookidoo_module

M = "http://mealie.test:9000"
TODAY = date.today().isoformat()


class FakeCookidoo:
    """Behaves like cookidoo_api.Cookidoo for the calls the week shopping list makes."""

    def __init__(self):
        self.shopping = []
        self.down = False

    async def login(self):
        pass

    async def get_recipes_in_calendar_week(self, day):
        if self.down:
            raise ConnectionError("cookidoo down")
        recipes = [NS(id="c1", name="Lasagne", total_time="600", thumbnail=None, image=None, url="u"),
                   NS(id="c2", name="Suppe", total_time="600", thumbnail=None, image=None, url="u")]
        return [NS(id=TODAY, title=TODAY, recipes=recipes + recipes[:1], customer_recipe_ids=[])]  # c1 planned twice

    async def add_ingredient_items_for_recipes(self, recipe_ids):
        self.shopping.extend(recipe_ids)
        return [NS(id=f"x{i}", name="Zutat") for i in range(2 * len(recipe_ids))]


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
    from app.services import config_store
    from app.services.mealie import mealie_service

    monkeypatch.setitem(config_store._extra, "MEALIE_URL", M)
    monkeypatch.setitem(config_store._extra, "MEALIE_TOKEN", "t")
    mealie_service._group_slug = None
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        http.get(f"{M}/api/groups/self").mock(return_value=httpx.Response(200, json={"slug": "home", "id": "g1", "name": "Home"}))
        http.get(f"{M}/api/households/shopping/lists").mock(
            return_value=httpx.Response(200, json={"items": [{"id": "L1", "name": "Einkauf"}]}))
        http.plan = http.get(f"{M}/api/households/mealplans")  # one route; tests change what it answers
        yield http


def _mealie_plan(http):
    http.plan.mock(return_value=httpx.Response(200, json={"items": [
        {"id": 1, "date": TODAY, "entryType": "dinner", "recipeId": "m1", "recipe": {"id": "m1", "name": "Shakshuka", "slug": "s"}},
        {"id": 2, "date": TODAY, "entryType": "lunch", "recipeId": "m1", "recipe": {"id": "m1", "name": "Shakshuka", "slug": "s"}},
        {"id": 3, "date": TODAY, "entryType": "side", "title": "Reste", "recipeId": None, "recipe": None}]}))
    return http.post(f"{M}/api/households/shopping/lists/L1/recipe/m1").mock(return_value=httpx.Response(200, json={}))


def _hub_recipe(client, h):
    rid = client.post("/api/recipes", headers=h, json={"title": "Chili", "ingredients": ["Mais", "Bohnen"]}).json()["id"]
    client.post("/api/meals/plan", headers=h, json={"date": TODAY, "recipe_id": rid})


def test_all_sources_in_one_call(client, auth, cookidoo, mealie, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "homeassistant_url", None)
    _hub_recipe(client, auth)
    post = _mealie_plan(mealie)
    r = client.post("/api/meals/shopping-list", headers=auth).json()
    by = {s["source"]: s for s in r["sources"]}
    assert set(by) == {"hub", "cookidoo", "mealie"} and all(s["status"] == "ok" for s in by.values())
    assert cookidoo.shopping == ["c1", "c2"]  # each recipe once although planned twice
    assert post.call_count == 1 and by["mealie"]["recipes"] == 1
    assert by["cookidoo"]["added"] == 4 and by["hub"]["added"] >= 2
    assert r["added"] == sum(s["added"] for s in by.values())
    assert r["message"] == "Einkaufsliste aktualisiert."
    assert "Cookidoo: 2 Rezepte" in by["cookidoo"]["message"]


def test_one_source_down_does_not_block_the_others(client, auth, cookidoo, mealie, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "homeassistant_url", None)
    _hub_recipe(client, auth)
    mealie.plan.mock(side_effect=httpx.ConnectError("down"))
    r = client.post("/api/meals/shopping-list", headers=auth).json()
    by = {s["source"]: s for s in r["sources"]}
    assert by["mealie"]["status"] == "unavailable" and by["cookidoo"]["status"] == "ok" and by["hub"]["status"] == "ok"
    assert cookidoo.shopping == ["c1", "c2"] and r["message"] == "Einkaufsliste teilweise aktualisiert."

    cookidoo.down = True
    cookidoo.shopping.clear()
    r = client.post("/api/meals/shopping-list", headers=auth).json()
    assert {s["source"]: s["status"] for s in r["sources"]}["cookidoo"] == "unavailable"
    assert {s["source"]: s["status"] for s in r["sources"]}["hub"] == "ok"


FAR = "?start=2098-01-01&end=2098-01-07"  # no hub entries there (the test database is shared)


def test_only_external_recipes_and_nothing_planned(client, auth, mealie):
    mealie.plan.mock(return_value=httpx.Response(200, json={"items": []}))
    r = client.post(f"/api/meals/shopping-list{FAR}", headers=auth).json()
    assert r["sources"] == [] and r["message"] == "Keine Rezepte im Zeitraum geplant."
    post = _mealie_plan(mealie)
    r = client.post(f"/api/meals/shopping-list{FAR}", headers=auth).json()
    assert [s["source"] for s in r["sources"]] == ["mealie"] and post.call_count == 1 and r["ingredients"] == []


def test_explicit_range_and_english_messages(client, auth, mealie):
    plan = mealie.plan.mock(return_value=httpx.Response(200, json={"items": []}))
    client.post("/api/meals/shopping-list?start=2098-01-01&end=2098-01-09", headers=auth)
    assert plan.calls.last.request.url.params["end_date"] == "2098-01-09"
    _mealie_plan(mealie)
    r = client.post(f"/api/meals/shopping-list{FAR}", headers={**auth, "Accept-Language": "en"}).json()
    assert r["sources"][0]["message"] == "Mealie: 1 recipes added to the shopping list."
    assert r["message"] == "Shopping list updated."
