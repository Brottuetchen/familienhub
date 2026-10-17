"""Themes: mitgelieferte Farbschemata, Installation aus GitHub nur für Admins und nur sicher (#36)."""

import json

import httpx
import pytest

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User
from app.routers import themes as themes_router

GOOD = {
    "name": "Waldgrün",
    "colors": {"primary": "#2E7D32", "secondary": "#A5D6A7", "background": "#0B1F0E", "surface": "#13301A",
               "surfaceHigh": "#1C4224", "border": "#2C5A35"},
}


def _auth(client, name, role="partner"):
    with SessionLocal() as db:
        if not db.query(User).filter(User.username == name).first():
            db.add(User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"), role=role))
            db.commit()
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def remote(monkeypatch):
    """Gefälschtes GitHub: merkt sich die abgerufene URL, liefert eine konfigurierbare Antwort."""
    state = {"calls": [], "status": 200, "body": json.dumps(GOOD).encode(), "headers": {}}

    def handler(request: httpx.Request):
        state["calls"].append(str(request.url))
        return httpx.Response(state["status"], content=state["body"], headers=state["headers"])

    monkeypatch.setattr(themes_router, "_transport", lambda: httpx.MockTransport(handler))
    return state


def test_list_requires_login_and_has_builtins(client):
    assert client.get("/api/themes").status_code == 401
    items = client.get("/api/themes", headers=_auth(client, "th_a")).json()["items"]
    names = {t["name"] for t in items}
    assert {"Liquid Glass", "Clean Cards", "Neo-Brutalism"} <= names
    assert all(t["builtin"] for t in items if t["name"] == "Liquid Glass")
    lg = next(t for t in items if t["name"] == "Liquid Glass")
    assert lg["id"] == "builtin:liquid-glass" and lg["colors"]["primary"].startswith("#")


def test_install_only_for_admins(client, auth, remote):
    r = client.post("/api/themes", headers=_auth(client, "th_b"), json={"url": "https://github.com/a/b"})
    assert r.status_code == 403 and remote["calls"] == []


def test_install_from_github_repo_url(client, auth, remote):
    r = client.post("/api/themes", headers=auth, json={"url": "https://github.com/familie/themes/tree/main/wald"})
    assert r.status_code == 201, r.text
    assert remote["calls"] == ["https://raw.githubusercontent.com/familie/themes/main/wald/theme.json"]
    t = r.json()
    assert t["name"] == "Waldgrün" and t["builtin"] is False and t["id"].startswith("custom:")
    assert any(x["id"] == t["id"] for x in client.get("/api/themes", headers=_auth(client, "th_c")).json()["items"])
    # gleiches Theme noch einmal → 409
    assert client.post("/api/themes", headers=auth, json={"url": "https://github.com/familie/themes/tree/main/wald"}).status_code == 409


@pytest.mark.parametrize("url", [
    "http://raw.githubusercontent.com/a/b/main/theme.json",      # kein https
    "https://192.168.1.82:8123/api/states",                    # internes Ziel
    "https://example.com/theme.json",                            # fremder Host
    "https://raw.githubusercontent.com.evil.test/a/b/main/theme.json",
    "https://user:pw@raw.githubusercontent.com/a/b/main/theme.json",
    "https://raw.githubusercontent.com/../../etc/passwd",
    "file:///etc/passwd",
])
def test_install_rejects_non_github_urls(client, auth, remote, url):
    r = client.post("/api/themes", headers=auth, json={"url": url})
    assert r.status_code == 422, (url, r.text)
    assert remote["calls"] == []


@pytest.mark.parametrize("change", [
    {"colors": {**GOOD["colors"], "primary": "red"}},                 # keine Hex-Farbe
    {"colors": {k: v for k, v in GOOD["colors"].items() if k != "surface"}},  # Pflichtfeld fehlt
    {"name": ""},
    {"name": "x" * 61},
    {"colors": {**GOOD["colors"], "primary": "#2E7D32; background:url(http://x)"}},
])
def test_install_rejects_invalid_theme_json(client, auth, remote, change):
    remote["body"] = json.dumps({**GOOD, **change}).encode()
    r = client.post("/api/themes", headers=auth, json={"url": "https://raw.githubusercontent.com/a/b/main/theme.json"})
    assert r.status_code == 422, r.text


def test_install_rejects_redirects_large_and_non_json(client, auth, remote):
    url = "https://raw.githubusercontent.com/a/b/main/theme.json"
    remote.update(status=302, headers={"location": "http://192.168.1.1/"})
    assert client.post("/api/themes", headers=auth, json={"url": url}).status_code == 422
    remote.update(status=200, headers={}, body=b"{" + b" " * 70_000 + b"}")
    assert client.post("/api/themes", headers=auth, json={"url": url}).status_code == 422
    remote.update(body=b"<html>kein json</html>")
    assert client.post("/api/themes", headers=auth, json={"url": url}).status_code == 422


def test_unknown_fields_are_dropped(client, auth, remote):
    remote["body"] = json.dumps({**GOOD, "name": "Mit Extras", "script": "alert(1)",
                                 "colors": {**GOOD["colors"], "evil": "#000000"}}).encode()
    t = client.post("/api/themes", headers=auth, json={"url": "https://raw.githubusercontent.com/a/b/main/x/theme.json"}).json()
    assert "script" not in t and "evil" not in t["colors"]


def test_delete_custom_admin_only_builtin_never(client, auth, remote):
    remote["body"] = json.dumps({**GOOD, "name": "Zum Löschen"}).encode()
    tid = client.post("/api/themes", headers=auth, json={"url": "https://raw.githubusercontent.com/a/b/main/del/theme.json"}).json()["id"]
    assert client.delete(f"/api/themes/{tid}", headers=_auth(client, "th_d")).status_code == 403
    assert client.delete("/api/themes/builtin:liquid-glass", headers=auth).status_code == 403
    assert client.delete(f"/api/themes/{tid}", headers=auth).status_code == 200
    assert client.delete(f"/api/themes/{tid}", headers=auth).status_code == 404


# ── Designsprache (style) ──────────────────────────────────────────────────

from app.routers.themes import validate_theme  # noqa: E402

STYLE = {
    "background": {"type": "glow", "colors": ["#7C3AED", "#22D3EE"]},
    "card": {"radius": 20, "border": 1, "shadow": "none", "glass": True, "header": "plain"},
    "accents": ["#8B5CF6", "#F59E0B"],
    "nav": "floating",
    "layout": "bento",
    "titleWeight": 700,
    "uppercaseTitles": True,
}


# Seit „Schrift im Theme“: ohne Angabe überall die Systemschrift
SYSTEM_FONTS = {"title": "system", "body": "system", "label": "system"}


def test_style_is_kept_when_valid():
    t = validate_theme({**GOOD, "style": STYLE})
    assert t["style"] == {**STYLE, "background": {"type": "glow", "colors": ["#7C3AED", "#22D3EE"]},
                          "accents": ["#8B5CF6", "#F59E0B"], "font": SYSTEM_FONTS}


def test_style_defaults_when_missing():
    assert validate_theme(GOOD)["style"] == {
        "background": {"type": "solid", "colors": []},
        "card": {"radius": 20, "border": 1, "shadow": "none", "glass": False, "header": "plain"},
        "accents": [], "nav": "bar", "layout": "list", "titleWeight": 500, "uppercaseTitles": False,
        "font": SYSTEM_FONTS,
    }


@pytest.mark.parametrize("bad", [
    {"background": {"type": "video", "colors": []}},
    {"background": {"type": "glow", "colors": ["url(http://x)"]}},
    {"background": {"type": "glow", "colors": ["#000000"] * 5}},
    {"card": {"radius": 100}},
    {"card": {"border": 9}},
    {"card": {"shadow": "inset 0 0 9px red"}},
    {"card": {"header": "html"}},
    {"accents": ["#000000"] * 7},
    {"nav": "sidebar"},
    {"layout": "grid3d"},
    {"titleWeight": 950},
    {"titleWeight": "bold"},
    {"uppercaseTitles": "ja"},
])
def test_style_rejects_unknown_values(bad):
    with pytest.raises(ValueError):
        validate_theme({**GOOD, "style": {**STYLE, **bad}})


def test_style_unknown_keys_dropped():
    t = validate_theme({**GOOD, "style": {**STYLE, "css": "body{}", "card": {**STYLE["card"], "onclick": "x"}}})
    assert "css" not in t["style"] and "onclick" not in t["style"]["card"]


def test_builtins_cover_the_four_design_languages(client):
    items = {t["id"]: t for t in validate_builtins()}
    assert set(items) >= {"builtin:liquid-glass", "builtin:clean-cards", "builtin:neo-brutalism", "builtin:warm"}
    assert items["builtin:liquid-glass"]["style"]["card"]["glass"] is True
    assert items["builtin:neo-brutalism"]["style"]["card"]["shadow"] == "hard"
    assert items["builtin:neo-brutalism"]["style"]["card"]["header"] == "band"
    assert items["builtin:clean-cards"]["style"]["nav"] == "floating"
    assert items["builtin:clean-cards"]["style"]["layout"] == "bento"


def validate_builtins():
    from app.routers.themes import builtin_themes

    builtin_themes.cache_clear()
    return builtin_themes()


# ── Hell/Dunkel-Varianten ─────────────────────────────────────────────────

from app.routers.themes import builtin_themes, validate_theme  # noqa: E402

_LIGHT = {"primary": "#C8381B", "secondary": "#141414", "background": "#EFECE6", "surface": "#F5F3EE",
          "surfaceHigh": "#E5E1D8", "border": "#D3CEC3"}
_DARK = {"primary": "#E0482A", "secondary": "#EDEAE3", "background": "#121212", "surface": "#1A1A1A",
         "surfaceHigh": "#242424", "border": "#2E2E2E"}


def test_variant_style_only_overrides_given_fields():
    t = validate_theme({"name": "Präzision", "colors": _LIGHT,
                        "style": {"card": {"radius": 0, "border": 1}, "layout": "bento", "titleWeight": 800},
                        "variants": {"dark": {"colors": _DARK, "style": {"card": {"border": 2}}}}})
    dark = t["variants"]["dark"]
    assert dark["colors"]["background"] == "#121212"
    assert dark["style"]["card"]["radius"] == 0 and dark["style"]["card"]["border"] == 2  # Radius geerbt
    assert dark["style"]["layout"] == "bento" and dark["style"]["titleWeight"] == 800


@pytest.mark.parametrize("variants,msg", [
    ({"sepia": {"colors": _DARK}}, "variants"),
    ({}, "variants"),
    ({"dark": {"colors": {**_DARK, "border": "rot"}}}, "variants.dark.colors"),
    ({"dark": {"style": {}}}, "variants.dark.colors"),
    ({"dark": {"colors": _DARK, "style": {"card": {"radius": 99}}}}, "card.radius"),
])
def test_invalid_variants_rejected(variants, msg):
    with pytest.raises(ValueError, match=msg.replace(".", r"\.")):
        validate_theme({"name": "X", "colors": _LIGHT, "variants": variants})


def test_themes_without_variants_still_valid():
    assert "variants" not in validate_theme({"name": "Alt", "colors": _LIGHT})


def test_builtin_themes_offer_light_and_dark():
    for t in builtin_themes():
        assert len(t["variants"]) == 1, t["name"]  # Grundfassung + die jeweils andere


# ── Schriften ─────────────────────────────────────────────────────────────


def test_font_defaults_to_system_and_accepts_known_fonts():
    assert validate_theme({"name": "X", "colors": _LIGHT})["style"]["font"] == {"title": "system", "body": "system", "label": "system"}
    t = validate_theme({"name": "X", "colors": _LIGHT, "style": {"font": {"title": "grotesk", "label": "mono"}}})
    assert t["style"]["font"] == {"title": "grotesk", "body": "system", "label": "mono"}


@pytest.mark.parametrize("font", [{"title": "Comic Sans"}, {"title": "https://evil.example/font.ttf"}, {"heading": "pixel"}, "pixel"])
def test_unknown_fonts_rejected(font):
    with pytest.raises(ValueError, match="font"):
        validate_theme({"name": "X", "colors": _LIGHT, "style": {"font": font}})


def test_pixel_builtin_uses_pixel_font_in_both_modes():
    pixel = next(t for t in builtin_themes() if t["name"] == "Pixel")
    assert pixel["style"]["font"]["title"] == "pixel" and pixel["style"]["card"]["shadow"] == "hard"
    assert pixel["variants"]["dark"]["style"]["font"]["title"] == "pixel"
