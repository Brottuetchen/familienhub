"""Notice about a newer release (Administration → Updates). GitHub is mocked."""

import httpx
import pytest
import respx

from app import __version__
from app.config import settings
from app.core.database import SessionLocal
from app.models.config import ConfigOverride
from app.services import update_check

API = "https://api.github.com/repos/Brottuetchen/familienhub/releases"


def _github():
    """Mocked GitHub; calls to the hub itself (the test client) pass through."""
    router = respx.mock(using="httpx", assert_all_mocked=False, assert_all_called=False)
    router.route(host="testserver").pass_through()
    return router


def _rel(tag, pre=False, draft=False):
    return {"tag_name": tag, "name": f"Familienhub {tag}", "prerelease": pre, "draft": draft,
            "html_url": f"https://github.com/Brottuetchen/familienhub/releases/tag/{tag}",
            "published_at": "2026-10-01T10:00:00Z"}


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.setattr(settings, "update_check", True)
    monkeypatch.setattr(settings, "update_check_repo", "Brottuetchen/familienhub")
    monkeypatch.setattr(update_check, "__version__", "1.0.0")
    update_check.reset()
    yield
    update_check.reset()
    with SessionLocal() as db:  # settings saved through the API must not leak into the next test
        db.query(ConfigOverride).filter(ConfigOverride.key.like("UPDATE_CHECK%")).delete(synchronize_session=False)
        db.commit()


def test_only_admins(client):
    from tests.test_backup import _user

    h = _user(client, "up_partner")
    assert client.get("/api/admin/update", headers=h).status_code == 403
    assert client.get("/api/admin/update").status_code == 401
    assert client.put("/api/admin/update/settings", headers=h, json={"enabled": False}).status_code == 403


def test_newer_release_is_reported(client, auth):
    with _github() as http:
        route = http.get(url__startswith=API).respond(json=[_rel("v1.2.0"), _rel("v1.1.0"), _rel("v0.9.0")])
        r = client.get("/api/admin/update", headers=auth).json()
        assert route.called
    assert r["available"] is True and r["latest"] == "1.2.0" and r["current"] == "1.0.0"
    assert r["url"].endswith("/releases/tag/v1.2.0")
    assert r["docker_command"] == "docker compose pull && docker compose up -d"
    assert r["status"] == "ok" and r["enabled"] is True


def test_up_to_date(client, auth):
    with _github() as http:
        http.get(url__startswith=API).respond(json=[_rel("v1.0.0"), _rel("v0.9.0")])
        r = client.get("/api/admin/update", headers=auth).json()
    assert r["available"] is False and r["status"] == "ok" and r["latest"] is None


def test_prereleases_only_for_prerelease_users(client, auth, monkeypatch):
    releases = [_rel("v1.1.0-beta.1", pre=True), _rel("v1.0.0")]
    with _github() as http:
        http.get(url__startswith=API).respond(json=releases)
        assert client.get("/api/admin/update", headers=auth).json()["available"] is False
    update_check.reset()
    monkeypatch.setattr(update_check, "__version__", "1.0.0-beta.1")
    with _github() as http:
        http.get(url__startswith=API).respond(json=[_rel("v1.0.0-beta.2", pre=True), _rel("v1.0.0-beta.1", pre=True)])
        r = client.get("/api/admin/update", headers=auth).json()
    assert r["available"] and r["latest"] == "1.0.0-beta.2" and r["prerelease"] is True
    assert "FAMILIENHUB_VERSION=1.0.0-beta.2" in r["docker_command"]


def test_drafts_and_odd_tags_are_ignored(client, auth):
    with _github() as http:
        http.get(url__startswith=API).respond(json=[_rel("v9.0.0", draft=True), _rel("nightly"), _rel("v1.0.1")])
        r = client.get("/api/admin/update", headers=auth).json()
    assert r["latest"] == "1.0.1"


def test_result_is_cached(client, auth):
    with _github() as http:
        route = http.get(url__startswith=API).respond(json=[_rel("v1.2.0")])
        for _ in range(3):
            assert client.get("/api/admin/update", headers=auth).json()["available"]
        assert route.call_count == 1


def test_github_failure_is_soft_and_cached(client, auth):
    with _github() as http:
        route = http.get(url__startswith=API).mock(side_effect=httpx.ConnectError("down"))
        for _ in range(2):
            r = client.get("/api/admin/update", headers=auth)
            assert r.status_code == 200 and r.json()["status"] == "unavailable" and r.json()["available"] is False
        assert route.call_count == 1
    update_check.reset()
    with _github() as http:
        http.get(url__startswith=API).respond(status_code=403, json={"message": "rate limited"})
        assert client.get("/api/admin/update", headers=auth).json()["status"] == "unavailable"
    update_check.reset()
    with _github() as http:
        http.get(url__startswith=API).respond(text="<html>")
        assert client.get("/api/admin/update", headers=auth).json()["status"] == "unavailable"


def test_switched_off_makes_no_request(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "update_check", "false")
    with _github() as http:
        route = http.get(url__startswith=API)
        r = client.get("/api/admin/update", headers=auth).json()
        assert not route.called
    assert r["status"] == "off" and r["enabled"] is False and r["available"] is False


def test_development_build_has_nothing_to_compare(client, auth, monkeypatch):
    monkeypatch.setattr(update_check, "__version__", "dev")
    with _github() as http:
        route = http.get(url__startswith=API)
        assert client.get("/api/admin/update", headers=auth).json()["status"] == "unknown_version"
        assert not route.called


def test_repo_is_configurable_and_validated(client, auth):
    with _github() as http:
        route = http.get(url__startswith="https://api.github.com/repos/someone/fork/releases").respond(json=[_rel("v1.5.0")])
        r = client.put("/api/admin/update/settings", headers=auth, json={"enabled": True, "repo": "someone/fork"}).json()
        assert route.called and r["repo"] == "someone/fork" and r["latest"] == "1.5.0"
    assert client.put("/api/admin/update/settings", headers=auth,
                      json={"enabled": True, "repo": "../etc/passwd"}).status_code == 422
    with _github() as http:
        http.get(url__startswith=API).respond(json=[])
        r = client.put("/api/admin/update/settings", headers=auth, json={"enabled": False, "repo": ""}).json()
    assert r["repo"] == "Brottuetchen/familienhub" and r["enabled"] is False


def test_foreign_release_links_are_not_passed_on(client, auth):
    bad = _rel("v1.2.0")
    bad["html_url"] = "https://evil.example/phish"
    with _github() as http:
        http.get(url__startswith=API).respond(json=[bad])
        r = client.get("/api/admin/update", headers=auth).json()
    assert r["url"] == "https://github.com/Brottuetchen/familienhub/releases/tag/v1.2.0"


def test_running_version_comes_from_the_package():
    assert isinstance(__version__, str)
