"""Plugin pages: manifest field, signed short-lived links, the served route with its headers and path rules."""

import asyncio
import base64
import json
import time

import pytest

from app.config import settings
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User
from app.plugins import Page, Plugin, hooks
from app.plugins.manifest import pages_for, validate_manifest
from app.plugins.registry import plugin_registry
from app.services import plugin_pages

MANIFEST = {"id": "pg_demo", "name": "Pages", "version": "1.0.0", "description": "d", "author": "a",
            "entry_point": "x.y:Z"}
HTML = b"<!doctype html><title>Recap</title><script>1</script>"


class Pages(Plugin):
    def __init__(self):
        super().__init__(id="pg_demo", name="Pages demo",
                         pages=(Page("recap", {"de": "Rückblick", "en": "Recap"}, "star"),
                                Page("plain", "Einfach")))
        self.calls = []
        self.reply = None

    async def page(self, user, page_id, path):
        self.calls.append((user.id, page_id, path))
        if self.reply is not None:
            return await self.reply(user, page_id, path)
        if path == "":
            return "text/html; charset=utf-8", HTML
        if path == "app.js":
            return "application/javascript", b"console.log(1)"
        if path == "clip.mp4":
            return "video/mp4", bytes(range(100))
        return None


@pytest.fixture
def plug():
    plugin = Pages()
    assert plugin_registry.register(plugin)
    yield plugin
    plugin_registry.unregister(plugin.id)


def person(client, name, role="partner"):
    with SessionLocal() as db:
        if not db.query(User).filter(User.username == name).first():
            db.add(User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"),
                        role=role, full_name=name.title()))
            db.commit()
        uid = db.query(User).filter(User.username == name).first().id
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}, uid


def link(client, headers, page="recap", plugin="pg_demo", **body):
    r = client.post(f"/api/plugin-pages/{plugin}/{page}/link", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()["url"]


# --- manifest ---

def test_manifest_pages_validated_and_defaulted():
    m = validate_manifest({**MANIFEST, "pages": [{"id": "recap", "title": {"de": "Rückblick", "en": "Recap"},
                                                  "icon": "star"}, {"id": "two", "title": "Zwei"}]})
    assert m["pages"][1] == {"id": "two", "title": "Zwei", "icon": "extension"}
    pages = pages_for(m)
    assert pages[0] == Page("recap", {"de": "Rückblick", "en": "Recap"}, "star")


@pytest.mark.parametrize("bad", [
    [{"id": "Recap", "title": "x"}],                      # upper case
    [{"id": "../x", "title": "x"}],
    [{"id": "a", "title": "x", "icon": "skull"}],         # not in the icon allow-list
    [{"id": "a", "title": "x", "extra": 1}],
    [{"id": "a"}],                                        # no title
    [{"id": "a", "title": "x"}, {"id": "a", "title": "y"}],
    [{"id": f"p{i}", "title": "x"} for i in range(11)],
    "nope",
])
def test_manifest_rejects_bad_pages(bad):
    with pytest.raises(ValueError):
        validate_manifest({**MANIFEST, "pages": bad})


# --- token ---

def test_token_roundtrip_and_binding():
    token = plugin_pages.create_token(7, "pg_demo", "recap")
    assert plugin_pages.verify_token(token) == (7, "pg_demo", "recap")


def test_token_tampering_is_refused():
    token = plugin_pages.create_token(7, "pg_demo", "recap")
    payload, sig = token.split(".")
    forged = base64.urlsafe_b64encode(json.dumps([1, "pg_demo", "recap", int(time.time()) + 999]).encode()).rstrip(b"=")
    assert plugin_pages.verify_token(f"{forged.decode()}.{sig}") is None
    assert plugin_pages.verify_token(f"{payload}.{sig[:-2]}AA") is None
    for junk in ("", "x", "a.b.c", payload, "." + sig, payload + ".", "é.é", "A" * 500):
        assert plugin_pages.verify_token(junk) is None


def test_token_expires_and_changes_with_the_secret(monkeypatch):
    token = plugin_pages.create_token(7, "pg_demo", "recap", now=1000)
    assert plugin_pages.verify_token(token, now=1000 + plugin_pages.TOKEN_TTL - 1)
    with pytest.raises(plugin_pages.Expired):
        plugin_pages.verify_token(token, now=1000 + plugin_pages.TOKEN_TTL)
    monkeypatch.setattr(settings, "secret_key", "another-secret-key")
    assert plugin_pages.verify_token(token, now=1000) is None


def test_token_is_not_a_login_token():
    from app.core.security import verify_token

    assert verify_token(plugin_pages.create_token(7, "pg_demo", "recap")) is None


def test_range_parsing():
    assert plugin_pages.parse_range(None, 100) is None
    assert plugin_pages.parse_range("bytes=0-9", 100) == (0, 9)
    assert plugin_pages.parse_range("bytes=90-", 100) == (90, 99)
    assert plugin_pages.parse_range("bytes=-10", 100) == (90, 99)
    assert plugin_pages.parse_range("bytes=50-500", 100) == (50, 99)
    assert plugin_pages.parse_range("bytes=0-1,5-6", 100) is None
    for bad in ("bytes=100-", "bytes=9-3", "bytes=x-y", "bytes=-0"):
        with pytest.raises(ValueError):
            plugin_pages.parse_range(bad, 100)


# --- listing and links ---

def test_listing_is_localised_and_only_for_active_plugins(client, plug):
    headers, _ = person(client, "pg_a")
    items = [i for i in client.get("/api/plugin-pages", headers=headers).json()["items"] if i["plugin"] == "pg_demo"]
    assert [(i["id"], i["title"], i["icon"]) for i in items] == [("recap", "Rückblick", "star"),
                                                                 ("plain", "Einfach", "extension")]
    en = client.get("/api/plugin-pages", headers={**headers, "X-App-Language": "en"}).json()["items"]
    assert [i["title"] for i in en if i["plugin"] == "pg_demo"][0] == "Recap"
    settings.plugins_disabled = "pg_demo"
    try:
        assert not [i for i in client.get("/api/plugin-pages", headers=headers).json()["items"]
                    if i["plugin"] == "pg_demo"]
    finally:
        settings.plugins_disabled = ""
    assert client.get("/api/plugin-pages").status_code in (401, 403)


def test_link_needs_login_an_active_plugin_and_a_declared_page(client, plug):
    headers, _ = person(client, "pg_a")
    assert client.post("/api/plugin-pages/pg_demo/recap/link").status_code in (401, 403)
    assert client.post("/api/plugin-pages/pg_demo/missing/link", headers=headers).status_code == 404
    assert client.post("/api/plugin-pages/nothere/recap/link", headers=headers).status_code == 404
    assert client.post("/api/plugin-pages/pg_demo/../x/link", headers=headers).status_code in (404, 405)
    settings.plugins_disabled = "pg_demo"
    try:
        assert client.post("/api/plugin-pages/pg_demo/recap/link", headers=headers).status_code == 404
    finally:
        settings.plugins_disabled = ""
    r = client.post("/api/plugin-pages/pg_demo/recap/link", headers=headers)
    assert r.json()["url"].startswith("/plugin-pages/") and r.json()["url"].endswith("/")
    assert r.json()["expires_in"] == plugin_pages.TOKEN_TTL


def test_link_with_a_path_and_bad_paths(client, plug):
    headers, _ = person(client, "pg_a")
    assert link(client, headers, path="2026-10/index.html").endswith("/2026-10/index.html")
    for bad in ("../x", "a/../b", "a//b", "a\\b", "%2e%2e/x", "a\nb"):
        r = client.post("/api/plugin-pages/pg_demo/recap/link", headers=headers, json={"path": bad})
        assert r.status_code == 422, bad


# --- serving ---

def test_serves_page_without_bearer_with_strict_headers(client, plug):
    headers, uid = person(client, "pg_a")
    url = link(client, headers)
    r = client.get(url)  # no Authorization header
    assert r.status_code == 200 and r.content == HTML
    assert r.headers["content-type"] == "text/html; charset=utf-8"
    csp = r.headers["content-security-policy"]
    for part in ("default-src 'self'", "script-src 'self' 'unsafe-inline'", "style-src 'self' 'unsafe-inline'",
                 "media-src 'self'", "img-src 'self' data:"):
        assert part in csp
    assert "http" not in csp
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["cache-control"] == "private, no-store"
    assert plug.calls[-1] == (uid, "recap", "")


def test_relative_assets_use_the_same_token(client, plug):
    headers, _ = person(client, "pg_a")
    base = link(client, headers)
    r = client.get(base + "app.js")
    assert r.status_code == 200 and r.content == b"console.log(1)"
    assert r.headers["content-type"].startswith("application/javascript")
    assert r.headers["content-security-policy"] and r.headers["cache-control"] == "private, no-store"
    assert client.get(base + "missing.css").status_code == 404


def test_without_trailing_slash_redirects(client, plug):
    headers, _ = person(client, "pg_a")
    url = link(client, headers).rstrip("/")
    r = client.get(url, follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == url.rsplit("/", 1)[1] + "/"
    assert client.get(url).status_code == 200


def test_path_from_the_link_reaches_the_hook(client, plug):
    headers, _ = person(client, "pg_a")
    client.get(link(client, headers, path="app.js"))
    assert plug.calls[-1][2] == "app.js"


@pytest.mark.parametrize("suffix", ["%2e%2e/x", "%2E%2E%2Fx", "a%2fb", "a%5cb", "%00", "a%252fb", "a//b", "%2e",
                                    "a\\b"])
def test_path_traversal_is_refused_and_never_reaches_the_plugin(client, plug, suffix):
    headers, _ = person(client, "pg_a")
    base = link(client, headers)
    before = len(plug.calls)
    r = client.get(base + suffix)
    assert r.status_code in (400, 404), (suffix, r.status_code)
    assert len(plug.calls) == before


@pytest.mark.parametrize("path", ["../x", "a/../x", "./x", "a/./b", "a//b", "/abs", "a\\b", "a%2fb", "x\x00", "x\ny",
                                  "..", ".", "a/..", "//", "a" * 301, 5, None])
def test_clean_page_path_refuses_what_could_escape(path):
    """httpx resolves dot segments before sending, so the unit is checked directly."""
    assert hooks.clean_page_path(path) is None


def test_clean_page_path_accepts_normal_paths():
    for ok in ("", "app.js", "2026-10/cover.jpg", "reports/", "a b/c.png", "ü.png"):
        assert hooks.clean_page_path(ok) == ok


def test_forged_expired_and_foreign_tokens_get_nothing(client, plug):
    headers, uid = person(client, "pg_a")
    good = link(client, headers)
    token = good.split("/")[2]
    assert client.get(f"/plugin-pages/{token[:-3]}abc/").status_code == 404
    assert client.get("/plugin-pages/garbage/").status_code == 404
    old = plugin_pages.create_token(uid, "pg_demo", "recap", now=time.time() - 3600)
    r = client.get(f"/plugin-pages/{old}/")
    assert r.status_code == 410 and "abgelaufen" in r.json()["detail"]
    other = plugin_pages.create_token(uid, "pg_demo", "undeclared")
    assert client.get(f"/plugin-pages/{other}/").status_code == 404
    assert not any(c[1] == "undeclared" for c in plug.calls)


def test_token_stops_working_when_plugin_inactive_removed_or_person_deactivated(client, plug):
    headers, uid = person(client, "pg_gone")
    url = link(client, headers)
    assert client.get(url).status_code == 200
    settings.plugins_disabled = "pg_demo"
    try:
        assert client.get(url).status_code == 404
    finally:
        settings.plugins_disabled = ""
    with SessionLocal() as db:
        db.get(User, uid).is_active = False
        db.commit()
    try:
        assert client.get(url).status_code == 404
    finally:
        with SessionLocal() as db:
            db.get(User, uid).is_active = True
            db.commit()
    plugin_registry.unregister("pg_demo")
    assert client.get(url).status_code == 404
    plugin_registry.register(plug)


def test_the_token_serves_only_its_own_person(client, plug):
    a, ida = person(client, "pg_a")
    b, idb = person(client, "pg_b")
    client.get(link(client, a))
    client.get(link(client, b))
    assert [c[0] for c in plug.calls[-2:]] == [ida, idb]


def test_plugin_failures_are_404_without_details(client, plug):
    headers, _ = person(client, "pg_a")
    url = link(client, headers)

    async def boom(user, page_id, path):
        raise RuntimeError("secret-in-message")

    plug.reply = boom
    r = client.get(url)
    assert r.status_code == 404 and "secret-in-message" not in r.text


def test_slow_plugin_is_cut_off(client, plug, monkeypatch):
    headers, _ = person(client, "pg_a")
    url = link(client, headers)
    monkeypatch.setattr(hooks, "PAGE_TIMEOUT", 0.05)

    async def slow(user, page_id, path):
        await asyncio.sleep(2)
        return "text/html", b"late"

    plug.reply = slow
    assert client.get(url).status_code == 404


@pytest.mark.parametrize("reply", [
    ("text/html", "str body"), ("text/html",), "text/html", ("bad type", b"x"), ("text/html\r\nX-A: b", b"x"),
    (None, b"x"), ("text/html", None), 5,
])
def test_unusable_plugin_results_are_404(client, plug, reply):
    headers, _ = person(client, "pg_a")
    url = link(client, headers)

    async def answer(user, page_id, path):
        return reply

    plug.reply = answer
    assert client.get(url).status_code == 404


def test_oversized_results_are_refused(client, plug, monkeypatch):
    headers, _ = person(client, "pg_a")
    url = link(client, headers)
    monkeypatch.setattr(hooks, "MAX_PAGE_BYTES", 10)

    async def big(user, page_id, path):
        return "text/html", b"x" * 11

    plug.reply = big
    assert client.get(url).status_code == 404
    assert hooks.sanitize_page(("text/html", b"x" * 10)) == ("text/html", b"x" * 10)
    assert hooks.MAX_PAGE_BYTES == 10


def test_byte_range_requests_for_media(client, plug):
    headers, _ = person(client, "pg_a")
    base = link(client, headers)
    full = client.get(base + "clip.mp4")
    assert full.status_code == 200 and full.headers["accept-ranges"] == "bytes" and len(full.content) == 100
    part = client.get(base + "clip.mp4", headers={"Range": "bytes=10-19"})
    assert part.status_code == 206 and part.content == bytes(range(10, 20))
    assert part.headers["content-range"] == "bytes 10-19/100"
    assert part.headers["content-security-policy"]
    assert client.get(base + "clip.mp4", headers={"Range": "bytes=500-"}).status_code == 416


def test_head_request(client, plug):
    headers, _ = person(client, "pg_a")
    r = client.head(link(client, headers))
    assert r.status_code == 200 and r.content == b"" and r.headers["x-content-type-options"] == "nosniff"


def test_the_frontend_does_not_swallow_the_route(client, plug, tmp_path):
    """The web app's static files are mounted at "/" (as in production, after all routers): the page route must
    still win, and a path that is no page must not fall through to index.html."""
    from app.main import app, mount_frontend

    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "manifest.json").write_text('{"name": "x", "short_name": "x"}')
    (tmp_path / "push-sw.js").write_text("//")
    before = len(app.router.routes)
    assert mount_frontend(app, tmp_path)
    try:
        headers, _ = person(client, "pg_a")
        page = client.get(link(client, headers))
        assert page.status_code == 200 and page.content == HTML
        assert page.headers["content-security-policy"].startswith("default-src 'self'")
        gone = client.get("/plugin-pages/garbage/anything")
        assert gone.status_code == 404 and "app" not in gone.text
        assert client.get("/").status_code == 200  # the web app itself still works
    finally:
        del app.router.routes[before:]


def test_plugin_notification_can_carry_the_page_route():
    from app.plugins.api import _payload

    assert _payload(None, {"route": "/plugin-page/pg_demo/recap?path=2026-10"})["route"] == \
        "/plugin-page/pg_demo/recap?path=2026-10"
