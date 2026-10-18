"""Seerr: notify the requester when a wish becomes available, by polling (Seerr's only webhook slot may be taken)."""

import asyncio

import httpx
import pytest
import respx

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User
from app.routers import media

SE = "http://seerr-watch.test"
USERS = [{"id": 2, "username": "Sw_Anna", "jellyfinUsername": "Sw_Anna", "displayName": "Anna", "email": "anna@sw"},
         {"id": 7, "username": None, "jellyfinUsername": "fremd", "displayName": "Fremd", "email": "f@sw"}]


def _req(rid, user_id, tmdb=603, kind="movie", status=5):
    return {"id": rid, "type": kind, "media": {"tmdbId": tmdb, "status": status, "mediaType": kind}, "requestedBy": {"id": user_id}}


@pytest.fixture
def seerr(monkeypatch):
    from app.models.seerr_notice import SeerrNotice

    monkeypatch.setenv("SEERR_URL", SE)
    monkeypatch.setenv("SEERR_API_KEY", "k")
    media._users_cache.update(at=0.0, base=None, users=[])
    media._meta_cache.clear()
    with SessionLocal() as db:
        db.query(SeerrNotice).delete()
        if not db.query(User).filter(User.username == "sw_anna").first():
            db.add(User(username="sw_anna", email="sw_anna@test.de", hashed_password=get_password_hash("pw-12345"), role="partner"))
        db.commit()
    state = {"requests": []}
    sent = []

    async def fake_notify(user_id, title, body, **kw):
        sent.append((user_id, title))

    monkeypatch.setattr("app.services.seerr_watch.notify", fake_notify)
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.get(f"{SE}/api/v1/user").mock(return_value=httpx.Response(200, json={"results": USERS}))
        def requests_route(r):
            if state.get("down"):
                raise httpx.ConnectError("down")
            return httpx.Response(200, json={"results": state["requests"]})

        http.get(f"{SE}/api/v1/request").mock(side_effect=requests_route)
        http.get(f"{SE}/api/v1/movie/603").mock(return_value=httpx.Response(200, json={"title": "Matrix", "releaseDate": "1999-03-30"}))
        http.get(f"{SE}/api/v1/tv/1399").mock(return_value=httpx.Response(200, json={"name": "Game of Thrones"}))
        yield state, sent


def _run():
    from app.services.seerr_watch import check_available

    return asyncio.run(check_available())


def _anna():
    with SessionLocal() as db:
        return db.query(User).filter(User.username == "sw_anna").first().id


def test_first_run_remembers_silently_then_notifies_new(seerr):
    state, sent = seerr
    state["requests"] = [_req(1, 2)]
    assert _run() == 0 and sent == []  # already available before: no flood on first start
    state["requests"] = [_req(1, 2), _req(2, 2, tmdb=1399, kind="tv")]
    assert _run() == 1
    assert sent == [(_anna(), "🎬 „Game of Thrones“ ist da")]
    assert _run() == 0  # not twice


def test_unknown_requester_and_partial_are_skipped(seerr):
    state, sent = seerr
    state["requests"] = []
    _run()  # seed
    state["requests"] = [_req(3, 7), _req(4, 2, status=4)]
    assert _run() == 0 and sent == []


def test_webhook_and_poll_do_not_double_notify(client, seerr, monkeypatch):
    state, sent = seerr
    state["requests"] = []
    _run()  # seed
    from app.models.service_key import ServiceKey

    raw = ServiceKey.generate()
    with SessionLocal() as db:
        db.add(ServiceKey(name="seerr-sw", key_hash=ServiceKey.hash(raw), hint=raw[-4:]))
        db.commit()
    monkeypatch.setattr(media, "notify", lambda *a, **k: asyncio.sleep(0))
    payload = {"notification_type": "MEDIA_AVAILABLE", "subject": "Matrix (1999)",
               "request": {"request_id": "5", "requestedBy_username": "Sw_Anna", "requestedBy_email": "anna@sw"}}
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        http.get(f"{SE}/api/v1/user").mock(return_value=httpx.Response(200, json={"results": USERS}))
        assert client.post("/api/media/webhook", json=payload, headers={"Authorization": f"Bearer {raw}"}).status_code == 200
    state["requests"] = [_req(5, 2)]
    assert _run() == 0 and sent == []


def test_inactive_without_seerr(monkeypatch):
    monkeypatch.delenv("SEERR_URL", raising=False)
    assert _run() == 0


def test_seerr_down_is_quiet(seerr, monkeypatch):
    state, sent = seerr
    state["down"] = True
    assert _run() == 0 and sent == []
