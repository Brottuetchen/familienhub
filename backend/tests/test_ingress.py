"""Sub-path hosting (#28): Home Assistant ingress sends X-Ingress-Path and strips the prefix itself."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app, mount_frontend

TOKEN = "AbC-123_xyz"
PREFIX = f"/api/hassio_ingress/{TOKEN}"
HA_PEER = ("172.30.32.2", 50000)


@pytest.fixture
def web(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text(
        '<html><head><base href="/"><title>Familienhub</title></head><body></body></html>', encoding="utf-8")
    (tmp_path / "manifest.json").write_text(json.dumps({
        "name": "Familienhub", "short_name": "Familienhub", "id": "/", "start_url": "/", "scope": "/",
        "icons": [{"src": "icons/Icon-192.png"}],
        "share_target": {"action": "/"}, "shortcuts": [{"name": "Einkauf", "url": "/?route=/shopping"}],
    }), encoding="utf-8")
    (tmp_path / "push-sw.js").write_text("// sw", encoding="utf-8")
    monkeypatch.setattr(settings, "trust_ingress_header", True)
    monkeypatch.setattr(settings, "root_path", "")
    target = FastAPI()
    assert mount_frontend(target, tmp_path)
    return target


def client(web, peer=HA_PEER):
    return TestClient(web, client=peer)


def test_direct_access_unchanged(web):
    r = client(web, ("192.168.1.5", 1)).get("/")
    assert '<base href="/">' in r.text
    manifest = client(web).get("/manifest.json").json()
    assert manifest["start_url"] == "/" and manifest["share_target"]["action"] == "/"


def test_header_rewrites_base_href_and_manifest(web):
    c = client(web)
    r = c.get("/", headers={"X-Ingress-Path": PREFIX})
    assert f'<base href="{PREFIX}/">' in r.text and '<base href="/">' not in r.text
    manifest = c.get("/manifest.json", headers={"X-Ingress-Path": PREFIX}).json()
    assert manifest["start_url"] == manifest["scope"] == manifest["id"] == f"{PREFIX}/"
    assert manifest["share_target"]["action"] == PREFIX + "/"
    assert manifest["shortcuts"][0]["url"] == f"{PREFIX}/?route=/shopping"
    assert manifest["icons"][0]["src"] == "icons/Icon-192.png"  # relative, resolved against the manifest URL
    assert c.get("/push-sw.js", headers={"X-Ingress-Path": PREFIX}).status_code == 200


def test_header_ignored_when_not_enabled(web, monkeypatch):
    monkeypatch.setattr(settings, "trust_ingress_header", False)
    r = client(web).get("/", headers={"X-Ingress-Path": PREFIX})
    assert '<base href="/">' in r.text


def test_header_ignored_from_untrusted_peer(web):
    r = client(web, ("192.168.1.5", 1)).get("/", headers={"X-Ingress-Path": PREFIX})
    assert '<base href="/">' in r.text


@pytest.mark.parametrize("bad", [
    '/"><script>alert(1)</script>', "//evil.example/x", "https://evil.example", "/api/hassio_ingress/",
    "/api/hassio_ingress/a/b", "/api/hassio_ingress/a b", "/api/hassio_ingress/a'b", "/api/hassio_ingress/<x>",
    "/other/prefix", "api/hassio_ingress/abc", "/api/hassio_ingress/../x", "/api/hassio_ingress/" + "a" * 200,
])
def test_invalid_header_rejected(web, bad):
    r = client(web).get("/", headers={"X-Ingress-Path": bad})
    assert r.status_code == 200
    assert '<base href="/">' in r.text and "evil" not in r.text and "<script>" not in r.text


def test_root_path_setting(web, monkeypatch):
    monkeypatch.setattr(settings, "root_path", "/hub/")
    r = client(web, ("192.168.1.5", 1)).get("/")
    assert '<base href="/hub/">' in r.text


@pytest.mark.parametrize("bad", ["hub", "//x", "/a/../b", '/a"b', "/a b", "http://x", "/<x>"])
def test_invalid_root_path_ignored(web, monkeypatch, bad):
    monkeypatch.setattr(settings, "root_path", bad)
    assert '<base href="/">' in client(web).get("/").text


def _cookie_paths(response):
    out = {}
    for raw in response.headers.get_list("set-cookie"):
        name = raw.split("=", 1)[0]
        out[name] = [p.strip()[5:] for p in raw.split(";") if p.strip().lower().startswith("path=")][0]
    return out


def test_api_and_cookie_path_under_prefix(admin_token, monkeypatch):
    """The proxy strips the prefix: API routes answer unchanged, auth cookies are scoped to the prefix."""
    monkeypatch.setattr(settings, "trust_ingress_header", True)
    creds = {"username": "admin", "password": "secret123"}
    with TestClient(app, client=HA_PEER) as c:
        assert c.get("/api/health", headers={"X-Ingress-Path": PREFIX}).status_code == 200
        r = c.post("/api/auth/login", json=creds, headers={"X-Ingress-Path": PREFIX})
        assert r.status_code == 200
        assert _cookie_paths(r) == {"access_token": PREFIX, "refresh_token": PREFIX}
        # Embedded in the HA iframe (same origin) - only through the trusted gateway
        assert r.headers["x-frame-options"] == "SAMEORIGIN"
        assert "frame-ancestors 'self'" in r.headers["content-security-policy"]
        # (the test client does not strip a prefix, so it would not send the prefix-scoped cookie: use the bearer token)
        out = c.post("/api/auth/logout", headers={"X-Ingress-Path": PREFIX, "Authorization": f"Bearer {admin_token}"})
        assert out.status_code in (200, 204) and set(_cookie_paths(out).values()) == {PREFIX}
    # Same request without the header (direct port): cookies at "/", still not frameable
    with TestClient(app, client=("192.168.1.5", 1)) as c:
        r = c.post("/api/auth/login", json=creds, headers={"X-Ingress-Path": PREFIX})
        assert _cookie_paths(r) == {"access_token": "/", "refresh_token": "/"}
        assert r.headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
