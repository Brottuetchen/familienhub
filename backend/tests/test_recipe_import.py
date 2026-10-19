"""Import a recipe from a link: schema.org parsing (JSON-LD, microdata), SSRF protection, preview endpoint."""

from pathlib import Path

import httpx
import pytest
import respx

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User
from app.services import safe_fetch
from app.services.recipe_import import parse_duration, parse_recipe

FIXTURES = Path(__file__).parent / "fixtures" / "recipes"
PAGE = "https://kochen.example.test/rezept/1"


def _fx(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def _auth(client, name, role="partner"):
    with SessionLocal() as db:
        if not db.query(User).filter(User.username == name).first():
            db.add(User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"), role=role))
            db.commit()
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    """Mocks the DNS system: example.test names are public, the names below are internal."""
    table = {"intranet.example.test": ["10.0.0.5"], "metadata.example.test": ["169.254.169.254"],
             "rebind.example.test": ["93.184.216.34", "127.0.0.1"], "v6.example.test": ["::1"]}

    async def resolve(host):
        return table.get(host, ["93.184.216.34"])

    monkeypatch.setattr(safe_fetch, "resolve", resolve)


@pytest.mark.parametrize("value,minutes", [
    ("PT15M", 15), ("PT1H30M", 90), ("P0DT45M", 45), ("P1DT2H", 1560), ("PT90S", 2), ("PT0M", None),
    ("1 hour", None), (None, None), (30, None), ("PT1.5H", 90)])
def test_iso_durations(value, minutes):
    assert parse_duration(value) == minutes


def test_graph_with_sections_and_object_images():
    r = parse_recipe(_fx("jsonld_graph.html"), PAGE)
    assert r["title"] == "Spaghetti Bolognese & mehr"
    assert r["description"] == "Klassiker für alle."
    assert r["servings"] == 4 and r["prep_minutes"] == 105
    assert r["ingredients"] == ["500 g Spaghetti", "400 g Hack", "2 Dosen Tomaten"]
    assert r["instructions"].splitlines() == ["Sauce:", "Hack anbraten.", "Tomaten zugeben.", "Nudeln:", "Spaghetti kochen."]
    assert r["image_url"] == "https://img.example.test/bolo.jpg"
    assert r["tags"] == "Hauptgericht, Pasta, Hackfleisch"
    assert r["source_url"] == PAGE


def test_top_level_array_string_instructions_and_protocol_relative_image():
    r = parse_recipe(_fx("jsonld_array.html"), PAGE)
    assert r["title"] == "Pfannkuchen" and r["servings"] == 6 and r["prep_minutes"] == 45
    assert r["instructions"].splitlines() == ["Teig anrühren.", "Ausbacken.", "Servieren."]
    assert r["image_url"] == "https://cdn.example.test/p.jpg"


def test_recipe_nested_in_article_with_relative_image():
    r = parse_recipe(_fx("jsonld_nested_author.html"), PAGE)
    assert r["title"] == "Apfelkuchen" and r["servings"] == 1 and r["prep_minutes"] == 60
    assert r["image_url"] == "https://kochen.example.test/img/kuchen.jpg"
    assert r["instructions"] == "Bei 180 Grad backen."


def test_microdata_fallback():
    r = parse_recipe(_fx("microdata.html"), PAGE)
    assert r["title"] == "Kürbissuppe" and r["servings"] == 4 and r["prep_minutes"] == 30
    assert r["ingredients"] == ["1 Kürbis", "1 Zwiebel"]
    assert r["instructions"].splitlines() == ["Kürbis würfeln.", "Kochen und pürieren."]
    assert r["image_url"] == "https://kochen.example.test/soup.jpg"


@pytest.mark.parametrize("name", ["no_recipe.html", "recipe_without_content.html"])
def test_pages_without_recipe_data(name):
    assert parse_recipe(_fx(name), PAGE) is None
    assert parse_recipe("", PAGE) is None
    assert parse_recipe("<<<not html", PAGE) is None


def _preview(client, h, url):
    return client.post("/api/recipes/import/preview", headers=h, json={"url": url})


def test_preview_returns_draft_and_saves_nothing(client):
    h = _auth(client, "imp_anna")
    before = len(client.get("/api/recipes", headers=h).json())
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        http.get(PAGE).mock(return_value=httpx.Response(200, text=_fx("jsonld_graph.html"), headers={"content-type": "text/html; charset=utf-8"}))
        res = _preview(client, h, PAGE)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok" and body["recipe"]["title"].startswith("Spaghetti")
    assert len(client.get("/api/recipes", headers=h).json()) == before
    # the draft can be saved as-is (edited) with the normal recipe endpoint, and keeps the picture
    saved = client.post("/api/recipes", headers=h, json=body["recipe"])
    assert saved.status_code == 200, saved.text
    assert saved.json()["image_url"] == "https://img.example.test/bolo.jpg"
    detail = client.get(f"/api/recipe-sources/hub/recipes/{saved.json()['id']}", headers=h).json()
    assert detail["image"] == "https://img.example.test/bolo.jpg" and detail["steps"][0] == "Sauce:"


def test_page_without_recipe_is_a_soft_message(client):
    h = _auth(client, "imp_ben")
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        http.get(PAGE).mock(return_value=httpx.Response(200, text=_fx("no_recipe.html")))
        assert _preview(client, h, PAGE).json() == {"status": "no_recipe", "recipe": None}


@pytest.mark.parametrize("url,status", [
    ("not a url", "invalid_url"), ("ftp://kochen.example.test/x", "invalid_url"),
    ("https://user:pw@kochen.example.test/x", "invalid_url"),
    ("http://127.0.0.1/x", "blocked"), ("http://localhost/x", "blocked"), ("http://[::1]/x", "blocked"),
    ("http://192.168.1.10/x", "blocked"), ("http://169.254.169.254/latest/meta-data", "blocked"),
    ("http://[::ffff:10.0.0.1]/x", "blocked"), ("http://0.0.0.0/x", "blocked"),
    ("https://intranet.example.test/x", "blocked"), ("https://metadata.example.test/x", "blocked"),
    ("https://rebind.example.test/x", "blocked"), ("https://v6.example.test/x", "blocked"),
    ("https://kochen.example.test:6379/x", "blocked")])
def test_ssrf_targets_are_refused_before_any_request(client, url, status):
    h = _auth(client, "imp_cara")
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        catch_all = http.route().mock(return_value=httpx.Response(200, text=_fx("jsonld_graph.html")))
        assert _preview(client, h, url).json() == {"status": status, "recipe": None}
        assert not catch_all.called


def test_redirect_to_internal_address_is_blocked(client):
    h = _auth(client, "imp_dora")
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        http.get(PAGE).mock(return_value=httpx.Response(302, headers={"location": "http://169.254.169.254/latest"}))
        internal = http.get("http://169.254.169.254/latest").mock(return_value=httpx.Response(200, text="secret"))
        assert _preview(client, h, PAGE).json()["status"] == "blocked"
        assert not internal.called


def test_redirect_to_public_page_is_followed(client):
    h = _auth(client, "imp_emil")
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        http.get(PAGE).mock(return_value=httpx.Response(301, headers={"location": "/rezept/neu"}))
        http.get("https://kochen.example.test/rezept/neu").mock(return_value=httpx.Response(200, text=_fx("jsonld_array.html")))
        body = _preview(client, h, PAGE).json()
    assert body["status"] == "ok" and body["recipe"]["source_url"] == "https://kochen.example.test/rezept/neu"


def test_redirect_loop_errors_and_size_limit(client):
    h = _auth(client, "imp_finn")
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        http.get(PAGE).mock(return_value=httpx.Response(302, headers={"location": PAGE}))
        assert _preview(client, h, PAGE).json()["status"] == "unreachable"
        http.get(PAGE).mock(return_value=httpx.Response(404))
        assert _preview(client, h, PAGE).json()["status"] == "unreachable"
        http.get(PAGE).mock(side_effect=httpx.ConnectTimeout("slow"))
        assert _preview(client, h, PAGE).json()["status"] == "unreachable"
        http.get(PAGE).mock(return_value=httpx.Response(200, content=b"x" * (safe_fetch.MAX_BYTES + 1)))
        assert _preview(client, h, PAGE).json()["status"] == "too_large"
        http.get(PAGE).mock(return_value=httpx.Response(200, content=b"\x89PNG", headers={"content-type": "image/png"}))
        assert _preview(client, h, PAGE).json()["status"] == "unreachable"


def test_child_may_not_import_and_anonymous_neither(client):
    child = _auth(client, "imp_kid", role="child")
    assert _preview(client, child, PAGE).status_code == 403
    assert client.post("/api/recipes/import/preview", json={"url": PAGE}).status_code in (401, 403)
