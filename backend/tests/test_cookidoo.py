"""Cookidoo-Plugin (#27): Suche, Wochenplan schreiben, Zutaten, Essen-Bereich (gefälschte Cookidoo-API)."""

from datetime import date, timedelta
from types import SimpleNamespace as NS

import pytest

from app.services import cookidoo as cookidoo_module


class AuthError(Exception):
    pass


class FakeCookidoo:
    """Verhält sich wie cookidoo_api.Cookidoo: total_time als Text in Sekunden, nur Tage mit Rezepten."""

    def __init__(self):
        self.logins = 0
        self.plan = {}  # "YYYY-MM-DD" -> [recipe]
        self.shopping = []
        self.expire_once = False

    async def login(self):
        self.logins += 1

    def _check(self):
        if self.expire_once:
            self.expire_once = False
            raise AuthError("token expired")

    @staticmethod
    def _recipe(rid, name):
        return NS(id=rid, name=name, total_time="4200.0", thumbnail=f"https://img/{rid}-t", image=f"https://img/{rid}",
                  url=f"https://cookidoo.test/recipes/recipe/de-DE/{rid}")

    async def search_recipes(self, query=None, *, page=None, **_):
        self._check()
        hits = [self._recipe("r1", "Lasagne"), self._recipe("r2", "Gemüse-Lasagne")]
        return NS(recipes=[h for h in hits if (query or "").lower() in h.name.lower()], total=2)

    async def get_recipes_in_calendar_week(self, day):
        self._check()
        monday = day - timedelta(days=day.weekday())
        out = []
        for i in range(7):
            d = (monday + timedelta(days=i)).isoformat()
            if self.plan.get(d):
                out.append(NS(id=d, title=d, recipes=list(self.plan[d]), customer_recipe_ids=[]))
        return out

    async def add_recipes_to_calendar(self, day, recipe_ids):
        self._check()
        for rid in recipe_ids:
            self.plan.setdefault(day.isoformat(), []).append(self._recipe(rid, {"r1": "Lasagne"}.get(rid, rid)))
        return NS(id=day.isoformat(), recipes=self.plan[day.isoformat()])

    async def remove_recipe_from_calendar(self, day, recipe_id):
        self._check()
        self.plan[day.isoformat()] = [r for r in self.plan.get(day.isoformat(), []) if r.id != recipe_id]
        return NS(id=day.isoformat(), recipes=self.plan[day.isoformat()])

    async def get_recipe_details(self, id):
        self._check()
        return NS(id=id, name="Lasagne", image="https://img/r1", thumbnail="https://img/r1-t", url="https://cookidoo.test/r1",
                  total_time=4200, active_time=1200, serving_size=4, difficulty="easy",
                  ingredients=[NS(id="i1", name="Hackfleisch", description="500 g"), NS(id="i2", name="Tomaten", description="2 Dosen")])

    async def add_ingredient_items_for_recipes(self, recipe_ids):
        self._check()
        self.shopping.extend(recipe_ids)
        return [NS(id=f"x{i}", name="Zutat") for i in range(3 * len(recipe_ids))]


@pytest.fixture
def fake(monkeypatch):
    client = FakeCookidoo()

    async def factory(cfg):
        assert cfg == {"email": "koch@test.de", "password": "geheim", "country": "de", "language": "de-DE"}
        return client

    monkeypatch.setenv("COOKIDOO_EMAIL", "koch@test.de")
    monkeypatch.setenv("COOKIDOO_PASSWORD", "geheim")
    monkeypatch.setattr(cookidoo_module, "AUTH_ERRORS", (AuthError,))
    monkeypatch.setattr(cookidoo_module.cookidoo_service, "_factory", factory)
    cookidoo_module.cookidoo_service.reset()
    yield client
    cookidoo_module.cookidoo_service.reset()


def test_not_configured_degrades_softly(client, auth, monkeypatch):
    monkeypatch.delenv("COOKIDOO_EMAIL", raising=False)
    monkeypatch.delenv("COOKIDOO_PASSWORD", raising=False)
    cookidoo_module.cookidoo_service.reset()
    r = client.get("/api/cookidoo/search?q=Lasagne", headers=auth)
    assert r.status_code == 200 and r.json()["status"] == "not_configured" and r.json()["items"] == []
    assert client.post("/api/cookidoo/plan", headers=auth, json={"date": "2026-10-20", "recipe_id": "r1"}).status_code == 503
    mods = client.get("/api/modules", headers=auth).json()["modules"]
    assert mods["meal_planning"]["enabled"] is False


def test_module_enabled_when_configured(client, auth, fake):
    mods = client.get("/api/modules", headers=auth).json()["modules"]
    assert mods["meal_planning"] == {"enabled": True, "core": False, "plugin": "cookidoo"}


def test_search_returns_items_and_requires_login(client, auth, fake):
    assert client.get("/api/cookidoo/search?q=Lasagne").status_code == 401
    r = client.get("/api/cookidoo/search?q=gemüse", headers=auth).json()
    assert r["status"] == "ok"
    assert r["items"] == [{"id": "r2", "name": "Gemüse-Lasagne", "image": "https://img/r2", "thumbnail": "https://img/r2-t",
                           "url": "https://cookidoo.test/recipes/recipe/de-DE/r2"}]
    assert fake.logins == 1
    client.get("/api/cookidoo/search?q=lasagne", headers=auth)
    assert fake.logins == 1  # Sitzung wird wiederverwendet


def test_expired_session_logs_in_again(client, auth, fake):
    client.get("/api/cookidoo/search?q=lasagne", headers=auth)
    fake.expire_once = True
    r = client.get("/api/cookidoo/search?q=lasagne", headers=auth).json()
    assert r["status"] == "ok" and len(r["items"]) == 2
    assert fake.logins == 2


def test_plan_add_shows_in_meals_and_remove(client, auth, fake):
    monday = date(2026, 10, 19)
    r = client.post("/api/cookidoo/plan", headers=auth, json={"date": "2026-10-21", "recipe_id": "r1"})
    assert r.status_code == 200
    assert fake.plan["2026-10-21"][0].id == "r1"

    week = client.get("/api/meals?week=2026-W43", headers=auth).json()
    assert week["status"] == "ok" and week["days"][0]["date"] == monday.isoformat()
    wed = week["days"][2]
    assert wed["date"] == "2026-10-21"
    assert wed["entries"] == [{"title": "Lasagne", "source": "cookidoo", "cookidoo_id": "r1", "minutes": 70,
                               "image": "https://img/r1-t", "url": "https://cookidoo.test/recipes/recipe/de-DE/r1"}]

    assert client.delete("/api/cookidoo/plan/2026-10-21/r1", headers=auth).status_code == 200
    assert fake.plan["2026-10-21"] == []
    assert client.get("/api/meals?week=2026-W43", headers=auth).json()["days"][2]["entries"] == []


def test_plan_rejects_bad_input(client, auth, fake):
    assert client.post("/api/cookidoo/plan", headers=auth, json={"date": "morgen", "recipe_id": "r1"}).status_code == 422
    assert client.post("/api/cookidoo/plan", headers=auth, json={"date": "2026-10-21", "recipe_id": ""}).status_code == 422


def test_recipe_details_and_ingredients_to_shopping(client, auth, fake):
    d = client.get("/api/cookidoo/recipes/r1", headers=auth).json()
    assert d["name"] == "Lasagne" and d["minutes"] == 70 and d["servings"] == 4
    assert d["ingredients"] == ["500 g Hackfleisch", "2 Dosen Tomaten"]
    r = client.post("/api/cookidoo/shopping", headers=auth, json={"recipe_ids": ["r1"]})
    assert r.json() == {"added": 3} and fake.shopping == ["r1"]


@pytest.mark.parametrize("method,path,payload", [
    ("GET", "/api/cookidoo/search?q=Lasagne", None),
    ("GET", "/api/cookidoo/recipes/r1", None),
    ("POST", "/api/cookidoo/plan", {"date": "2026-10-21", "recipe_id": "r1"}),
    ("DELETE", "/api/cookidoo/plan/2026-10-21/r1", None),
    ("POST", "/api/cookidoo/shopping", {"recipe_ids": ["r1"]}),
])
def test_disabled_plugin_never_calls_cookidoo(client, auth, fake, monkeypatch, method, path, payload):
    from app.config import settings

    # Auch eine bereits angemeldete Sitzung darf den Schalter nicht umgehen.
    assert client.get("/api/cookidoo/search?q=Lasagne", headers=auth).json()["status"] == "ok"
    calls = []
    check = fake._check

    def counted_check():
        calls.append(True)
        check()

    monkeypatch.setattr(fake, "_check", counted_check)
    monkeypatch.setattr(settings, "plugins_disabled", "cookidoo")
    response = client.request(method, path, headers=auth, json=payload)
    if path.startswith("/api/cookidoo/search"):
        assert response.status_code == 200
        assert response.json()["status"] == "unavailable"
        assert response.json()["items"] == []
    else:
        assert response.status_code == 503
    assert calls == []
    assert fake.logins == 1
    assert fake.plan == {} and fake.shopping == []


def test_cookidoo_error_is_reported_not_raised(client, auth, fake, monkeypatch):
    async def broken(*a, **k):
        raise RuntimeError("Cookidoo antwortet 500")

    monkeypatch.setattr(fake, "search_recipes", broken)
    monkeypatch.setattr(fake, "get_recipes_in_calendar_week", broken)
    r = client.get("/api/cookidoo/search?q=Suppe", headers=auth).json()
    assert r["status"] == "unavailable" and "500" in r["error"]
    week = client.get("/api/meals?week=2026-W43", headers=auth).json()
    assert week["status"] == "unavailable" and len(week["days"]) == 7  # eigene Einträge bleiben sichtbar


def test_relogin_closes_old_session(client, auth, fake, monkeypatch):
    class Session:
        closed = False

        async def close(self):
            self.closed = True

    made = []

    async def factory(cfg):
        c = FakeCookidoo()
        c._session = Session()
        made.append(c)
        return c

    monkeypatch.setattr(cookidoo_module.cookidoo_service, "_factory", factory)
    cookidoo_module.cookidoo_service.reset()
    client.get("/api/cookidoo/search?q=lasagne", headers=auth)
    made[0].expire_once = True
    assert client.get("/api/cookidoo/search?q=lasagne", headers=auth).json()["status"] == "ok"
    assert len(made) == 2 and made[0]._session.closed and not made[1]._session.closed
