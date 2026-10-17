"""Seerr-Plugin (#31): Suche, Wünsche im eigenen Namen (X-Api-User), Status, Webhook."""

import json

import httpx
import pytest
import respx

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.service_key import ServiceKey
from app.models.user import User
from app.routers import media

SE = "http://seerr.test"
KEY = "seerr-key"


def _auth(client, name, admin=False):
    with SessionLocal() as db:
        if not db.query(User).filter(User.username == name).first():
            db.add(User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"),
                        role="admin" if admin else "partner", is_admin=admin))
            db.commit()
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


USERS = [
    {"id": 1, "username": None, "jellyfinUsername": "md_admin", "displayName": "Admin", "email": "a@x"},
    {"id": 2, "username": "Md_Anna", "jellyfinUsername": "Md_Anna", "displayName": "Anna", "email": "anna@x"},
    {"id": 3, "username": None, "jellyfinUsername": "jemand", "displayName": "Ben", "email": "ben@x"},
]

MOVIE = {"id": 603, "mediaType": "movie", "title": "Matrix", "releaseDate": "1999-03-30", "posterPath": "/m.jpg",
         "overview": "Neo …", "mediaInfo": {"status": 5}}
SHOW = {"id": 1399, "mediaType": "tv", "name": "Game of Thrones", "firstAirDate": "2011-04-17", "posterPath": "/g.jpg"}
PERSON = {"id": 1, "mediaType": "person", "name": "Keanu"}


@pytest.fixture
def seerr(monkeypatch):
    monkeypatch.setenv("SEERR_URL", SE)
    monkeypatch.setenv("SEERR_API_KEY", KEY)
    media._users_cache.update(at=0.0, base=None, users=[])
    media._meta_cache.clear()
    seen = []
    requests = [
        {"id": 11, "status": 1, "type": "movie", "createdAt": "2026-10-17", "media": {"tmdbId": 603, "status": 2},
         "requestedBy": {"id": 2}},
        {"id": 12, "status": 2, "type": "tv", "createdAt": "2026-10-16", "media": {"tmdbId": 1399, "status": 5},
         "requestedBy": {"id": 2}},
        {"id": 13, "status": 1, "type": "movie", "createdAt": "2026-10-15", "media": {"tmdbId": 603, "status": 2},
         "requestedBy": {"id": 3}},
    ]
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()

        def guard(request):
            seen.append(request)
            if request.headers.get("X-Api-Key") != KEY:
                return httpx.Response(403, json={"message": "Kein Zugriff"})
            return None

        http.get(f"{SE}/api/v1/user").mock(side_effect=lambda r: guard(r) or httpx.Response(200, json={"results": USERS}))
        http.get(url__regex=rf"{SE}/api/v1/search.*").mock(
            side_effect=lambda r: guard(r) or httpx.Response(200, json={"results": [MOVIE, SHOW, PERSON]}))
        http.get(f"{SE}/api/v1/request").mock(
            side_effect=lambda r: guard(r) or httpx.Response(200, json={"results": requests}))
        http.get(f"{SE}/api/v1/movie/603").mock(side_effect=lambda r: guard(r) or httpx.Response(200, json=MOVIE))
        http.get(f"{SE}/api/v1/tv/1399").mock(side_effect=lambda r: guard(r) or httpx.Response(200, json=SHOW))

        def create(r):
            return guard(r) or httpx.Response(201, json={"id": 20, "status": 1})

        http.post(f"{SE}/api/v1/request").mock(side_effect=create)
        for req in requests:
            http.get(f"{SE}/api/v1/request/{req['id']}").mock(
                side_effect=lambda r, req=req: guard(r) or httpx.Response(200, json=req))
            http.delete(f"{SE}/api/v1/request/{req['id']}").mock(side_effect=lambda r: guard(r) or httpx.Response(204))
        yield seen


def _user_header(seen, path):
    return [r.headers.get("X-Api-User") for r in seen if r.url.path == path]


def test_not_configured(client, monkeypatch):
    monkeypatch.delenv("SEERR_URL", raising=False)
    h = _auth(client, "md_anna")
    assert client.get("/api/modules", headers=h).json()["modules"]["media_requests"]["enabled"] is False
    assert client.get("/api/media/search?q=matrix", headers=h).json()["status"] == "not_configured"


def test_search_acts_as_own_seerr_user_and_maps_status(client, seerr):
    h = _auth(client, "md_anna")
    data = client.get("/api/media/search?q=die matrix", headers=h).json()
    assert data["status"] == "ok"
    assert [i["title"] for i in data["items"]] == ["Matrix", "Game of Thrones"]  # Personen nicht
    movie, show = data["items"]
    assert movie == {"tmdb_id": 603, "media_type": "movie", "title": "Matrix", "year": 1999, "overview": "Neo …",
                     "poster": "https://image.tmdb.org/t/p/w342/m.jpg", "status": 5, "status_label": "Verfügbar",
                     "requestable": False}
    assert show["requestable"] is True and show["status"] is None
    search = [r for r in seerr if r.url.path == "/api/v1/search"][0]
    assert "query=die%20matrix" in str(search.url) and "language=de" in str(search.url)
    assert search.headers["X-Api-User"] == "2"


def test_unknown_user_gets_no_account_and_nothing_in_foreign_name(client, seerr):
    h = _auth(client, "md_niemand")
    data = client.get("/api/media/search?q=matrix", headers=h).json()
    assert data["status"] == "no_account" and data["items"] == []
    assert client.post("/api/media/requests", headers=h, json={"media_type": "movie", "tmdb_id": 603}).status_code == 403
    assert not [r for r in seerr if r.url.path in ("/api/v1/search", "/api/v1/request")]


def test_user_map(client, seerr, monkeypatch):
    monkeypatch.setenv("SEERR_USER_MAP", "md_benni=ben@x")
    h = _auth(client, "md_benni")
    client.get("/api/media/search?q=matrix", headers=h)
    assert _user_header(seerr, "/api/v1/search") == ["3"]


def test_my_requests_only_own_with_german_titles(client, seerr):
    h = _auth(client, "md_anna")
    data = client.get("/api/media/requests", headers=h).json()
    assert [(i["id"], i["title"], i["status_label"], i["can_cancel"]) for i in data["items"]] == [
        (11, "Matrix", "Wartet auf Freigabe", True),
        (12, "Game of Thrones", "Verfügbar", False),
    ]
    assert set(_user_header(seerr, "/api/v1/request")) == {"2"}


def test_create_request_in_own_name(client, seerr):
    h = _auth(client, "md_anna")
    r = client.post("/api/media/requests", headers=h, json={"media_type": "tv", "tmdb_id": 1399})
    assert r.status_code == 201 and r.json()["status_label"] == "Wartet auf Freigabe"
    post = [x for x in seerr if x.method == "POST"][0]
    assert post.headers["X-Api-User"] == "2"
    assert json.loads(post.content) == {"mediaType": "tv", "mediaId": 1399, "seasons": "all"}


@pytest.mark.parametrize("body", [{"media_type": "person", "tmdb_id": 1}, {"media_type": "movie", "tmdb_id": 0},
                                  {"media_type": "movie"}])
def test_create_request_validates(client, seerr, body):
    h = _auth(client, "md_anna")
    assert client.post("/api/media/requests", headers=h, json=body).status_code == 422


def test_cancel_only_own_pending(client, seerr):
    h = _auth(client, "md_anna")
    assert client.delete("/api/media/requests/13", headers=h).status_code == 404  # fremd
    assert client.delete("/api/media/requests/12", headers=h).status_code == 409  # schon freigegeben
    assert client.delete("/api/media/requests/11", headers=h).json() == {"deleted": True}
    assert [r.headers["X-Api-User"] for r in seerr if r.method == "DELETE"] == ["2"]


def test_unavailable_is_status(client, monkeypatch):
    monkeypatch.setenv("SEERR_URL", SE)
    monkeypatch.setenv("SEERR_API_KEY", KEY)
    media._users_cache.update(at=0.0, base=None, users=[])
    h = _auth(client, "md_anna")
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        http.get(f"{SE}/api/v1/user").mock(side_effect=httpx.ConnectError("geheim-intern"))
        data = client.get("/api/media/requests", headers=h).json()
    assert data["status"] == "unavailable" and "geheim" not in json.dumps(data)


def test_webhook_notifies_requester(client, seerr, monkeypatch):
    sent = []

    async def fake_notify(user_id, title, body, **kw):
        sent.append((user_id, title))

    monkeypatch.setattr(media, "notify", fake_notify)
    _auth(client, "md_anna")
    with SessionLocal() as db:
        anna = db.query(User).filter(User.username == "md_anna").first().id
    raw = _create_key()
    payload = {"notification_type": "MEDIA_AVAILABLE", "subject": "Matrix (1999)",
               "request": {"requestedBy_username": "Anna", "requestedBy_email": "anna@x"}}
    r = client.post("/api/media/webhook", json=payload, headers={"Authorization": f"Bearer {raw}"})
    assert r.status_code == 200 and r.json()["recipients"] == ["md_anna"]
    assert sent == [(anna, "🎬 „Matrix (1999)“ ist da")]
    assert client.post("/api/media/webhook", json=payload).status_code == 401
    assert client.post("/api/media/webhook", json={"notification_type": "MEDIA_PENDING"},
                       headers={"Authorization": f"Bearer {raw}"}).json() == {"ignored": "MEDIA_PENDING"}


def _create_key():
    raw = ServiceKey.generate()
    with SessionLocal() as db:
        db.add(ServiceKey(name="seerr", key_hash=ServiceKey.hash(raw), hint=raw[-4:]))
        db.commit()
    return raw
