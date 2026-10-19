"""#68: one details endpoint for the app's recipe quick view (hub recipe book, Cookidoo, Mealie)."""

import httpx
import pytest

from tests.test_cookidoo import fake  # noqa: F401  (fixture: fake Cookidoo account)
from tests.test_mealie import M, mealie  # noqa: F401  (fixture: mocked Mealie)

KEYS = {"status", "error", "id", "source", "title", "image", "minutes", "servings", "ingredients", "steps", "url"}


@pytest.fixture(autouse=True)
def _fresh_cache():
    from app.routers import recipe_sources

    recipe_sources._details.clear()
    yield
    recipe_sources._details.clear()


def test_hub_recipe_book(client, auth):
    made = client.post("/api/recipes", headers=auth, json={
        "title": "Pfannkuchen", "ingredients": ["200 g Mehl", "2 Eier"], "instructions": "Teig rühren\n\nBacken",
        "servings": 3, "prep_minutes": 25, "source_url": "https://example.org/p"}).json()
    r = client.get(f"/api/recipe-sources/hub/recipes/{made['id']}", headers=auth).json()
    assert set(r) == KEYS
    assert (r["status"], r["source"], r["title"], r["minutes"], r["servings"]) == ("ok", "hub", "Pfannkuchen", 25, 3)
    assert r["ingredients"] == ["200 g Mehl", "2 Eier"] and r["steps"] == ["Teig rühren", "Backen"]
    assert r["url"] == "https://example.org/p"
    assert client.get(f"/api/recipes/{made['id']}", headers=auth).status_code == 200


def test_hub_recipe_unknown_fails_softly(client, auth):
    for rid in ("999999", "abc"):
        r = client.get(f"/api/recipe-sources/hub/recipes/{rid}", headers=auth)
        assert r.status_code == 200 and r.json()["status"] == "unavailable" and r.json()["error"]


def test_cookidoo_details_are_cached(client, auth, fake):  # noqa: F811
    calls = []
    original = fake.get_recipe_details

    async def counted(id):
        calls.append(id)
        return await original(id)

    fake.get_recipe_details = counted
    r = client.get("/api/recipe-sources/cookidoo/recipes/r1", headers=auth).json()
    assert set(r) == KEYS
    assert (r["status"], r["source"], r["title"], r["minutes"], r["servings"]) == ("ok", "cookidoo", "Lasagne", 70, 4)
    assert r["ingredients"] == ["500 g Hackfleisch", "2 Dosen Tomaten"] and r["steps"] == []
    assert r["image"] == "https://img/r1" and r["url"] == "https://cookidoo.test/r1"
    assert client.get("/api/recipe-sources/cookidoo/recipes/r1", headers=auth).json() == r
    assert calls == ["r1"]  # second read from the cache
    client.get("/api/recipe-sources/cookidoo/recipes/r2", headers=auth)
    assert calls == ["r1", "r2"]


def test_cookidoo_failure_is_soft_and_not_cached(client, auth, fake):  # noqa: F811
    async def broken(id):
        raise RuntimeError("boom")

    ok = fake.get_recipe_details
    fake.get_recipe_details = broken
    r = client.get("/api/recipe-sources/cookidoo/recipes/r1", headers=auth)
    assert r.status_code == 200 and r.json()["status"] == "unavailable" and "Cookidoo" in r.json()["error"]
    fake.get_recipe_details = ok
    assert client.get("/api/recipe-sources/cookidoo/recipes/r1", headers=auth).json()["status"] == "ok"


def test_mealie_details(client, auth, mealie):  # noqa: F811
    route = mealie.get(f"{M}/api/recipes/r1").mock(return_value=httpx.Response(200, json={
        "id": "r1", "name": "Shakshuka", "slug": "shakshuka", "image": "abc", "totalTimeSeconds": 1800,
        "recipeServings": 4,
        "recipeIngredient": [{"display": "4 Eier"}, {"originalText": "1 Dose Tomaten"}, {"note": ""}],
        "recipeInstructions": [{"title": "Sauce", "text": "Tomaten kochen"}, {"text": "Eier einschlagen"}]}))
    r = client.get("/api/recipe-sources/mealie/recipes/r1", headers=auth).json()
    assert set(r) == KEYS
    assert (r["status"], r["title"], r["minutes"], r["servings"]) == ("ok", "Shakshuka", 30, 4)
    assert r["ingredients"] == ["4 Eier", "1 Dose Tomaten"]
    assert r["steps"] == ["Sauce Tomaten kochen", "Eier einschlagen"]
    assert r["url"] == "https://mealie.example.org/g/home/r/shakshuka"
    assert r["image"].startswith("https://mealie.example.org/api/media/recipes/r1/")
    assert route.calls.last.request.headers["Authorization"] == "Bearer mealie-token"
    client.get("/api/recipe-sources/mealie/recipes/r1", headers=auth)
    assert route.call_count == 1


def test_mealie_unreachable_or_missing(client, auth, mealie):  # noqa: F811
    mealie.get(f"{M}/api/recipes/gone").mock(return_value=httpx.Response(404, json={}))
    r = client.get("/api/recipe-sources/mealie/recipes/gone", headers=auth)
    assert r.status_code == 200 and r.json()["status"] == "unavailable" and "404" in r.json()["error"]
    mealie.get(f"{M}/api/recipes/down").mock(side_effect=httpx.ConnectError("no"))
    assert client.get("/api/recipe-sources/mealie/recipes/down", headers=auth).json()["status"] == "unavailable"


def test_inactive_source_and_login_are_required(client, auth):
    assert client.get("/api/recipe-sources/nope/recipes/1", headers=auth).status_code == 409
    assert client.get("/api/recipe-sources/hub/recipes/1").status_code in (401, 403)
