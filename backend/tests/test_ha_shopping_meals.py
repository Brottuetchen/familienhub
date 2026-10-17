"""Tests für Shopping und Meals über Home Assistant (WP 3b)."""


import pytest
import respx
from httpx import Response

from app.config import settings


@pytest.fixture
def mock_ha(monkeypatch):
    """Konfiguriert HA-Verbindung für Tests."""
    monkeypatch.setattr(settings, "homeassistant_url", "http://ha.test")
    monkeypatch.setattr(settings, "homeassistant_token", "test-token")
    monkeypatch.setattr(settings, "ha_shopping_todo", "todo.cookidoo_zusatzliche_kaufe")
    monkeypatch.setattr(settings, "ha_recipe_shopping_todo", "todo.cookidoo_einkaufsliste")
    monkeypatch.setattr(settings, "ha_mealplan_calendar", "calendar.cookidoo_speiseplan")


@respx.mock
def test_shopping_groups_manual_and_recipes(client, auth, mock_ha):
    """GET /api/shopping liefert zwei Gruppen: manual und recipes."""
    route = respx.route(
        host="ha.test",
        path__regex=r"/api/services/todo/get_items",
    ).mock(
        side_effect=[
            Response(
                200,
                json={
                    "service_response": {
                        "todo.cookidoo_zusatzliche_kaufe": {
                            "items": [
                                {"uid": "uid1", "summary": "Milch", "status": "needs_action"},
                                {"uid": "uid2", "summary": "Brot", "status": "completed"},
                            ]
                        }
                    }
                },
            ),
            Response(
                200,
                json={
                    "service_response": {
                        "todo.cookidoo_einkaufsliste": {
                            "items": [
                                {"uid": "uid3", "summary": "Mehl", "status": "needs_action"},
                            ]
                        }
                    }
                },
            ),
        ]
    )

    resp = client.get("/api/shopping", headers=auth)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["error"] is None
    assert len(data["groups"]) == 2

    manual_group = next(g for g in data["groups"] if g["key"] == "manual")
    assert manual_group["entity"] == "todo.cookidoo_zusatzliche_kaufe"
    assert len(manual_group["items"]) == 2

    recipes_group = next(g for g in data["groups"] if g["key"] == "recipes")
    assert recipes_group["entity"] == "todo.cookidoo_einkaufsliste"
    assert len(recipes_group["items"]) == 1

    assert route.call_count == 2


@respx.mock
def test_add_item_posts_to_shopping_todo(client, auth, mock_ha):
    """POST /api/shopping sendet an HA_SHOPPING_TODO."""
    route = respx.route(
        host="ha.test",
        path__regex=r"/api/services/todo/add_item",
    ).mock(return_value=Response(200, json={}))

    resp = client.post("/api/shopping", json={"item": "Butter"}, headers=auth)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    assert route.called
    request = route.calls.last.request
    body = request.content.decode()
    assert '"entity_id"' in body and "todo.cookidoo_zusatzliche_kaufe" in body
    assert '"item"' in body and "Butter" in body


@respx.mock
def test_toggle_uses_uid_not_summary(client, auth, mock_ha):
    """PATCH /api/shopping/{uid} sendet UID an HA, nicht den Text."""
    route = respx.route(
        host="ha.test",
        path__regex=r"/api/services/todo/update_item",
    ).mock(return_value=Response(200, json={}))

    resp = client.patch(
        "/api/shopping/uid123",
        json={"done": True},
        headers=auth,
    )
    assert resp.status_code == 200

    assert route.called
    request = route.calls.last.request
    body = request.content.decode()
    assert '"item"' in body and "uid123" in body
    assert '"status"' in body and "completed" in body


@respx.mock
def test_delete_only_manual(client, auth, mock_ha):
    """DELETE /api/shopping/{uid} funktioniert nur für manuelle Einträge."""
    # Mock für get_items (um Rezeptliste zu prüfen)
    get_items_route = respx.route(
        host="ha.test",
        path__regex=r"/api/services/todo/get_items",
    ).mock(
        return_value=Response(
            200,
            json={
                "service_response": {
                    "todo.cookidoo_einkaufsliste": {
                        "items": [
                            {"uid": "recipe-uid-789", "summary": "Mehl", "status": "needs_action"},
                        ]
                    }
                }
            },
        )
    )

    remove_route = respx.route(
        host="ha.test",
        path__regex=r"/api/services/todo/remove_item",
    ).mock(return_value=Response(200, json={}))

    # Versuch, Rezept-Eintrag zu löschen → 403
    resp = client.delete("/api/shopping/recipe-uid-789", headers=auth)
    assert resp.status_code == 403

    # Wichtig: KEIN remove_item-Aufruf an HA
    assert not remove_route.called, "remove_item darf nicht aufgerufen werden für Rezepteinträge"

    # Manueller Eintrag kann gelöscht werden
    # Mock anpassen: recipe-uid-789 nicht mehr in der Liste
    get_items_route.mock(
        return_value=Response(
            200,
            json={
                "service_response": {
                    "todo.cookidoo_einkaufsliste": {
                        "items": []
                    }
                }
            },
        )
    )

    resp = client.delete("/api/shopping/uid456", headers=auth)
    assert resp.status_code == 200

    assert remove_route.called
    request = remove_route.calls.last.request
    body = request.content.decode()
    assert '"entity_id"' in body and "todo.cookidoo_zusatzliche_kaufe" in body
    assert '"item"' in body and "uid456" in body


@respx.mock
def test_meals_week_merges_cookidoo_and_hub_sorted_by_day(client, auth, mock_ha):
    """GET /api/meals?week=YYYY-Www merged Cookidoo-Kalender und Hub-DB."""
    from app.core.database import SessionLocal
    from app.models.recipe import MealPlanEntry, Recipe

    # Hub-Eintrag in DB für 2024-01-16 anlegen
    db = SessionLocal()
    try:
        recipe = Recipe(
            title="Hub-Gericht",
            ingredients_json='["Kartoffeln"]',
            instructions="Kochen",
        )
        db.add(recipe)
        db.flush()

        entry = MealPlanEntry(
            date="2024-01-16",
            meal_type="lunch",
            recipe_id=recipe.id,
        )
        db.add(entry)
        db.commit()
    finally:
        db.close()

    respx.route(
        host="ha.test",
        path__regex=r"/api/calendars/calendar\.cookidoo_speiseplan",
    ).mock(
        return_value=Response(
            200,
            json=[
                {
                    "summary": "Pasta Carbonara",
                    "start": {"date": "2024-01-15"},
                    "end": {"date": "2024-01-15"},
                    "uid": "cookidoo-1",
                },
                {
                    "summary": "Pizza",
                    "start": {"date": "2024-01-16"},
                    "end": {"date": "2024-01-16"},
                    "uid": "cookidoo-2",
                },
            ],
        )
    )

    resp = client.get("/api/meals?week=2024-W03", headers=auth)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "days" in data

    # Prüfe dass days aufsteigend nach Datum sortiert ist
    dates = [day["date"] for day in data["days"]]
    assert dates == sorted(dates), "days müssen nach Datum aufsteigend sortiert sein"

    # Prüfe dass sowohl Cookidoo- als auch Hub-Einträge vorhanden sind
    all_entries = []
    for day in data["days"]:
        all_entries.extend(day["entries"])

    cookidoo_entries = [e for e in all_entries if e["source"] == "cookidoo"]
    hub_entries = [e for e in all_entries if e["source"] == "hub"]

    assert len(cookidoo_entries) == 2, "Zwei Cookidoo-Einträge erwartet"
    assert len(hub_entries) == 1, "Ein Hub-Eintrag erwartet"
    assert any(e["title"] == "Pasta Carbonara" for e in cookidoo_entries)
    assert any(e["title"] == "Hub-Gericht" for e in hub_entries)

    # Prüfe dass am 16.01. beide Einträge vorhanden sind (Hub + Cookidoo)
    day_16 = next((d for d in data["days"] if d["date"] == "2024-01-16"), None)
    assert day_16 is not None, "Tag 2024-01-16 muss in days enthalten sein"
    assert len(day_16["entries"]) == 2, "Am 16.01. müssen 2 Einträge sein (Hub + Cookidoo)"

    sources_on_16 = {e["source"] for e in day_16["entries"]}
    assert sources_on_16 == {"hub", "cookidoo"}, "Am 16.01. müssen Hub- und Cookidoo-Einträge sein"


@respx.mock
def test_cookidoo_entries_read_only(client, auth, mock_ha):
    """PATCH/DELETE auf Cookidoo-Einträge liefert 403."""
    from app.core.database import SessionLocal
    from app.models.recipe import MealPlanEntry, Recipe
    from datetime import date

    # Hub-Eintrag in DB anlegen
    db = SessionLocal()
    try:
        recipe = Recipe(
            title="Test-Rezept",
            ingredients_json='["Mehl", "Wasser"]',
            instructions="Mischen",
        )
        db.add(recipe)
        db.flush()

        entry = MealPlanEntry(
            date=date.today().isoformat(),
            meal_type="lunch",
            recipe_id=recipe.id,
        )
        db.add(entry)
        db.commit()
        hub_id = entry.id
    finally:
        db.close()

    # Cookidoo-ID mit Präfix
    cookidoo_id = "cookidoo:abc123"

    # PATCH auf Cookidoo-Eintrag → 403
    resp = client.patch(
        f"/api/meals/{cookidoo_id}",
        json={"meal_type": "dinner"},
        headers=auth,
    )
    assert resp.status_code == 403

    # DELETE auf Cookidoo-Eintrag → 403
    resp = client.delete(f"/api/meals/{cookidoo_id}", headers=auth)
    assert resp.status_code == 403

    # Hub-Eintrag ändern und löschen funktioniert
    resp = client.patch(
        f"/api/meals/{hub_id}",
        json={"meal_type": "dinner"},
        headers=auth,
    )
    assert resp.status_code == 200

    resp = client.delete(f"/api/meals/{hub_id}", headers=auth)
    assert resp.status_code == 200


@respx.mock
def test_ha_unreachable_returns_unavailable_not_500(client, auth, mock_ha):
    """HA nicht erreichbar → status: unavailable, nicht HTTP 500."""
    respx.route(
        host="ha.test",
        path__regex=r"/api/services/todo/get_items",
    ).mock(side_effect=Exception("Connection refused"))

    resp = client.get("/api/shopping", headers=auth)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unavailable"
    assert data["error"] is not None


@respx.mock
def test_missing_entity_returns_unavailable(client, auth, mock_ha):
    """HA antwortet 400/404 → status: unavailable."""
    respx.route(
        host="ha.test",
        path__regex=r"/api/services/todo/get_items",
    ).mock(return_value=Response(404, json={"error": "Entity not found"}))

    resp = client.get("/api/shopping", headers=auth)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unavailable"
    assert data["error"] is not None


@respx.mock
def test_week_plan_to_shopping_writes_to_ha(client, auth, mock_ha):
    """POST /api/meals/shopping-list schreibt Zutaten an HA."""
    from app.core.database import SessionLocal
    from app.models.recipe import MealPlanEntry, Recipe
    from datetime import date

    # Testdaten in DB
    db = SessionLocal()
    try:
        recipe = Recipe(
            title="Testgericht",
            ingredients_json='["Tomaten", "Zwiebeln"]',
            instructions="Kochen",
        )
        db.add(recipe)
        db.flush()

        today = date.today()
        entry = MealPlanEntry(
            date=today.isoformat(),
            meal_type="dinner",
            recipe_id=recipe.id,
        )
        db.add(entry)
        db.commit()
    finally:
        db.close()

    route = respx.route(
        host="ha.test",
        path__regex=r"/api/services/todo/add_item",
    ).mock(return_value=Response(200, json={}))

    resp = client.post("/api/meals/shopping-list", headers=auth)
    assert resp.status_code == 200
    data = resp.json()

    # Mit dem angelegten Rezept (2 Zutaten) muss added == 2 sein
    assert data["added"] == 2

    # Der HA-Mock muss genau zwei add_item-Aufrufe sehen
    assert route.call_count == 2

    # Prüfe dass an todo.cookidoo_zusatzliche_kaufe gesendet wurde
    for call in route.calls:
        body = call.request.content.decode()
        assert "todo.cookidoo_zusatzliche_kaufe" in body
        # Einer der beiden Aufrufe muss Tomaten enthalten, der andere Zwiebeln

    bodies = [call.request.content.decode() for call in route.calls]
    assert any("Tomaten" in b for b in bodies)
    assert any("Zwiebeln" in b for b in bodies)


@respx.mock
def test_recent_suggests_completed_items_newest_first_without_duplicates(client, auth, mock_ha):
    """Vorschläge = abgehakte freie Artikel, neueste zuerst, ohne Doppelte; fragt HA nach status completed."""
    import json as _json

    route = respx.route(host="ha.test", path__regex=r"/api/services/todo/get_items").mock(
        return_value=Response(200, json={"service_response": {"todo.cookidoo_zusatzliche_kaufe": {"items": [
            {"uid": "a", "summary": "Milch", "status": "completed"},
            {"uid": "b", "summary": "Brot", "status": "completed"},
            {"uid": "c", "summary": "milch", "status": "completed"},
        ]}}})
    )
    resp = client.get("/api/shopping/recent", headers=auth)
    assert resp.status_code == 200
    assert resp.json() == ["milch", "Brot"]
    sent = _json.loads(route.calls.last.request.content)
    assert sent == {"entity_id": "todo.cookidoo_zusatzliche_kaufe", "status": ["completed"]}


def test_recent_without_ha_is_empty(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "homeassistant_url", None)
    assert client.get("/api/shopping/recent", headers=auth).json() == []
