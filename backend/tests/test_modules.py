"""Kern-Module: eigener Essensplan mit Rezepten, Feiertage."""

from datetime import date


def test_recipes_and_meal_plan(client, auth):
    r = client.post(
        "/api/recipes",
        headers=auth,
        json={"title": "Spaghetti", "ingredients": ["500g Nudeln", "Tomaten"], "servings": 4},
    )
    assert r.status_code == 200
    recipe_id = r.json()["id"]
    assert r.json()["ingredients"] == ["500g Nudeln", "Tomaten"]

    today = date.today().isoformat()
    p = client.post("/api/meals/plan", headers=auth, json={"date": today, "recipe_id": recipe_id})
    assert p.status_code == 200

    # Neues Format seit WP 3b: {status, error, days: [{date, entries}]}
    plan = client.get("/api/meals", headers=auth).json()
    assert plan["status"] == "ok"
    all_entries = []
    for day in plan["days"]:
        all_entries.extend(day["entries"])
    assert any(e["title"] == "Spaghetti" and e["source"] == "hub" for e in all_entries)

    # Shopping list from the plan: without Home Assistant the ingredients go to the hub's own list (since 18.10.)
    sl = client.post("/api/meals/shopping-list?days=7", headers=auth).json()
    assert "500g Nudeln" in sl["ingredients"]
    assert sl["added"] >= 2


def test_holidays_endpoint(client, auth):
    hol = client.get("/api/calendar/holidays?days=365", headers=auth).json()
    names = {h["name"] for h in hol}
    assert "Neujahr" in names or "1. Weihnachtstag" in names
