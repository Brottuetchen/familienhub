"""Recipe book in the hub: recipes without any external service, planned onto days, ingredients to the shopping list."""

from datetime import date

import pytest

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User


def _auth(client, name, role="partner"):
    with SessionLocal() as db:
        if not db.query(User).filter(User.username == name).first():
            db.add(User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"), role=role))
            db.commit()
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def hub_list(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "homeassistant_url", None)


def _manual(client, h):
    groups = client.get("/api/shopping", headers=h).json()["groups"]
    return [i["summary"] for g in groups if g["key"] == "manual" for i in g["items"]]


def test_create_update_search_delete(client):
    h = _auth(client, "rb_anna")
    r = client.post("/api/recipes", headers=h, json={
        "title": "Linsencurry", "ingredients": ["200 g rote Linsen", "1 Dose Kokosmilch"], "instructions": "Alles köcheln.",
        "servings": 4, "prep_minutes": 30, "source_url": "https://example.org/curry"})
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    u = client.put(f"/api/recipes/{rid}", headers=h, json={"title": "Rotes Linsencurry", "ingredients": ["200 g rote Linsen"],
                                                             "servings": 2})
    assert u.status_code == 200 and u.json()["title"] == "Rotes Linsencurry" and u.json()["ingredients"] == ["200 g rote Linsen"]
    assert "Rotes Linsencurry" in {x["title"] for x in client.get("/api/recipes", params={"q": "linsen"}, headers=h).json()}
    assert "Rotes Linsencurry" not in {x["title"] for x in client.get("/api/recipes", params={"q": "pizza"}, headers=h).json()}
    assert client.delete(f"/api/recipes/{rid}", headers=h).status_code == 200
    assert client.get(f"/api/recipes/{rid}", headers=h).status_code == 404


@pytest.mark.parametrize("body", [
    {"title": ""},
    {"title": "x" * 201},
    {"title": "Ok", "ingredients": ["x"] * 101},
    {"title": "Ok", "servings": 0},
    {"title": "Ok", "source_url": "javascript:alert(1)"},
])
def test_validation(client, body):
    assert client.post("/api/recipes", headers=_auth(client, "rb_val"), json=body).status_code == 422


def test_children_and_guests_only_read(client):
    p = _auth(client, "rb_parent")
    rid = client.post("/api/recipes", headers=p, json={"title": "Pfannkuchen"}).json()["id"]
    for role in ("child", "guest"):
        h = _auth(client, f"rb_{role}", role)
        assert client.get(f"/api/recipes/{rid}", headers=h).status_code == 200
        assert client.put(f"/api/recipes/{rid}", headers=h, json={"title": "x"}).status_code == 403
        assert client.post(f"/api/recipes/{rid}/shopping", headers=h).status_code == 403


def test_recipe_ingredients_to_hub_shopping_list(client, hub_list):
    h = _auth(client, "rb_shop")
    rid = client.post("/api/recipes", headers=h, json={"title": "Pesto", "ingredients": ["Basilikum", "Pinienkerne", " "]}).json()["id"]
    r = client.post(f"/api/recipes/{rid}/shopping", headers=h)
    assert r.status_code == 200 and r.json()["added"] == 2
    assert {"Basilikum", "Pinienkerne"} <= set(_manual(client, h))


def test_week_plan_ingredients_go_to_the_current_list(client, hub_list):
    h = _auth(client, "rb_week")
    rid = client.post("/api/recipes", headers=h, json={"title": "Chili sin carne", "ingredients": ["Kidneybohnen", "Mais"]}).json()["id"]
    assert client.post("/api/meals/plan", headers=h, json={"date": date.today().isoformat(), "recipe_id": rid}).status_code == 200
    r = client.post("/api/meals/shopping-list?days=7", headers=h).json()
    assert "Kidneybohnen" in r["ingredients"] and r["added"] >= 2
    assert {"Kidneybohnen", "Mais"} <= set(_manual(client, h))


def test_planned_recipe_shows_in_week_with_recipe_id(client):
    h = _auth(client, "rb_plan")
    rid = client.post("/api/recipes", headers=h, json={"title": "Ofenkartoffeln", "prep_minutes": 45}).json()["id"]
    client.post("/api/meals/plan", headers=h, json={"date": date.today().isoformat(), "recipe_id": rid})
    entries = [e for d in client.get("/api/meals", headers=h).json()["days"] for e in d["entries"]]
    e = next(e for e in entries if e["title"] == "Ofenkartoffeln")
    assert e["source"] == "hub" and e["recipe_id"] == rid and e["minutes"] == 45
