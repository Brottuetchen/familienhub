"""Mealie as a source: recipe search and plan, household meal plan in the week, shopping list (API v2, mocked)."""

import json
from datetime import date

import httpx
import pytest
import respx

M = "http://mealie.test:9000"
TODAY = date.today().isoformat()


@pytest.fixture
def mealie(monkeypatch):
    from app.services import config_store
    from app.services.mealie import mealie_service

    monkeypatch.setitem(config_store._extra, "MEALIE_URL", M)
    monkeypatch.setitem(config_store._extra, "MEALIE_TOKEN", "mealie-token")
    monkeypatch.setitem(config_store._extra, "MEALIE_PUBLIC_URL", "https://mealie.example.org")
    mealie_service._group_slug = None
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        http.get(f"{M}/api/groups/self").mock(return_value=httpx.Response(200, json={"slug": "home", "id": "g1", "name": "Home"}))
        yield http


def _recipe(rid="r1", name="Shakshuka", slug="shakshuka"):
    return {"id": rid, "name": name, "slug": slug, "image": "abc", "totalTimeSeconds": 1800}


def test_recipe_sources_list_and_search(client, auth, mealie):
    route = mealie.get(f"{M}/api/recipes").mock(return_value=httpx.Response(200, json={"items": [_recipe()], "total": 1}))
    sources = client.get("/api/recipe-sources", headers=auth).json()
    assert {"id": "mealie", "name": "Mealie"} in sources
    r = client.get("/api/recipe-sources/mealie/search", params={"q": "shak"}, headers=auth).json()
    assert r["status"] == "ok" and r["items"][0]["name"] == "Shakshuka"
    assert r["items"][0]["url"] == "https://mealie.example.org/g/home/r/shakshuka"
    assert r["items"][0]["image"].startswith("https://mealie.example.org/api/media/recipes/r1/")
    assert route.calls.last.request.headers["Authorization"] == "Bearer mealie-token"
    assert route.calls.last.request.url.params["search"] == "shak"


def test_plan_and_unplan(client, auth, mealie):
    post = mealie.post(f"{M}/api/households/mealplans").mock(return_value=httpx.Response(201, json={"id": 9}))
    assert client.post("/api/recipe-sources/mealie/plan", headers=auth, json={"date": TODAY, "recipe_id": "r1"}).status_code == 200
    assert json.loads(post.calls.last.request.content) == {"date": TODAY, "entryType": "dinner", "recipeId": "r1"}

    mealie.get(f"{M}/api/households/mealplans").mock(return_value=httpx.Response(200, json={"items": [
        {"id": 9, "date": TODAY, "entryType": "dinner", "recipeId": "r1", "recipe": _recipe()}]}))
    delete = mealie.delete(f"{M}/api/households/mealplans/9").mock(return_value=httpx.Response(200, json={}))
    assert client.delete(f"/api/recipe-sources/mealie/plan/{TODAY}/r1", headers=auth).status_code == 200
    assert delete.called


def test_mealie_plan_entries_in_the_week(client, auth, mealie):
    mealie.get(f"{M}/api/households/mealplans").mock(return_value=httpx.Response(200, json={"items": [
        {"id": 9, "date": TODAY, "entryType": "dinner", "recipeId": "r1", "recipe": _recipe()},
        {"id": 10, "date": TODAY, "entryType": "lunch", "title": "Reste", "text": "vom Vortag", "recipeId": None, "recipe": None}]}))
    entries = [e for d in client.get("/api/meals", headers=auth).json()["days"] for e in d["entries"] if e["source"] == "mealie"]
    by_title = {e["title"]: e for e in entries}
    assert by_title["Shakshuka"]["recipe_id"] == "r1" and by_title["Shakshuka"]["minutes"] == 30
    assert by_title["Reste"]["description"] == "vom Vortag"


def test_mealie_down_keeps_other_entries(client, auth, mealie):
    mealie.get(f"{M}/api/households/mealplans").mock(side_effect=httpx.ConnectError("down"))
    r = client.get("/api/meals", headers=auth).json()
    assert r["status"] == "unavailable" and "Mealie" in r["error"] and len(r["days"]) == 7


def test_ingredients_to_mealie_list(client, auth, mealie):
    mealie.get(f"{M}/api/households/shopping/lists").mock(return_value=httpx.Response(200, json={"items": [
        {"id": "L0", "name": "Baumarkt"}, {"id": "L1", "name": "Einkauf"}]}))
    from app.services import config_store
    config_store._extra["MEALIE_SHOPPING_LIST"] = "einkauf"
    try:
        add = mealie.post(f"{M}/api/households/shopping/lists/L1/recipe/r1").mock(return_value=httpx.Response(200, json={}))
        r = client.post("/api/recipe-sources/mealie/shopping", headers=auth, json={"recipe_ids": ["r1"]})
        assert r.status_code == 200 and r.json() == {"added": 1} and add.called
    finally:
        config_store._extra.pop("MEALIE_SHOPPING_LIST", None)


def test_mealie_as_shopping_source(client, auth, mealie, monkeypatch):
    from app.services import config_store

    monkeypatch.setitem(config_store._extra, "SHOPPING_SOURCE", "mealie")
    mealie.get(f"{M}/api/households/shopping/lists").mock(return_value=httpx.Response(200, json={"items": [{"id": "L1", "name": "Einkauf"}]}))
    mealie.get(f"{M}/api/households/shopping/lists/L1").mock(return_value=httpx.Response(200, json={"id": "L1", "listItems": [
        {"id": "i1", "display": "Eier", "note": "Eier", "checked": False, "shoppingListId": "L1"},
        {"id": "i2", "display": "Mehl", "note": "Mehl", "checked": True, "shoppingListId": "L1"}]}))
    post = mealie.post(f"{M}/api/households/shopping/items").mock(return_value=httpx.Response(201, json={}))
    item = {"id": "i1", "display": "Eier", "note": "Eier", "checked": False, "shoppingListId": "L1", "quantity": 1}
    mealie.get(f"{M}/api/households/shopping/items/i1").mock(return_value=httpx.Response(200, json=item))
    put = mealie.put(f"{M}/api/households/shopping/items/i1").mock(return_value=httpx.Response(200, json={}))

    groups = client.get("/api/shopping", headers=auth).json()["groups"]
    items = {i["summary"]: i["status"] for i in groups[0]["items"]}
    assert items == {"Eier": "needs_action", "Mehl": "completed"}
    assert client.post("/api/shopping", headers=auth, json={"item": "Milch"}).status_code == 200
    assert json.loads(post.calls.last.request.content)["note"] == "Milch"
    assert client.patch("/api/shopping/i1", headers=auth, json={"done": True}).status_code == 200
    sent = json.loads(put.calls.last.request.content)
    assert sent["checked"] is True and sent["quantity"] == 1  # full item, only "checked" changed
    assert client.get("/api/shopping/recent", headers=auth).json() == ["Mehl"]
    assert client.get("/api/today", headers=auth).json()["shopping_open"] == 1


def test_rejected_token_is_reported(client, auth, mealie):
    mealie.get(f"{M}/api/recipes").mock(return_value=httpx.Response(401, json={"detail": "nope"}))
    r = client.get("/api/recipe-sources/mealie/search", params={"q": "abc"}, headers=auth).json()
    assert r["status"] == "unavailable" and "Token" in r["error"]


def test_inactive_source_and_roles(client, auth):
    assert client.get("/api/recipe-sources/mealie/search", params={"q": "abc"}, headers=auth).status_code == 409
    from app.core.database import SessionLocal
    from app.core.security import get_password_hash
    from app.models.user import User

    with SessionLocal() as db:
        if not db.query(User).filter(User.username == "mealie_kid").first():
            db.add(User(username="mealie_kid", email="mk@test.de", hashed_password=get_password_hash("pw-12345"), role="child"))
            db.commit()
    tok = client.post("/api/auth/login", json={"username": "mealie_kid", "password": "pw-12345"}).json()["access_token"]
    r = client.post("/api/recipe-sources/mealie/plan", headers={"Authorization": f"Bearer {tok}"}, json={"date": TODAY, "recipe_id": "r1"})
    assert r.status_code == 403
