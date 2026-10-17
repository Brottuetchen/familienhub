"""Bücher/Hörbücher über Shelfarr (gefälschte Shelfarr-API)."""

import pytest

from app.config import settings
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User
from app.routers import books


def _auth(client, name: str) -> dict:
    with SessionLocal() as db:
        if not db.query(User).filter(User.username == name).first():
            db.add(User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"), role="partner"))
            db.commit()
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _req(id_, user, title, status="searching", book_type="ebook"):
    return {"id": id_, "status": status, "attention_needed": False, "issue_description": None,
            "created_at": "2026-10-14T10:00:00Z", "book": {"title": title, "author": "A", "book_type": book_type},
            "user": {"id": 1, "username": user}}


@pytest.fixture
def shelf(monkeypatch):
    monkeypatch.setattr(settings, "shelfarr_url", "http://shelfarr.test")
    monkeypatch.setattr(settings, "shelfarr_token", "tok")
    calls = []
    store = {"requests": [_req(1, "book_a", "Momo"), _req(2, "book_b", "Fremdes Buch")]}

    async def fake(method, path, **kw):
        calls.append((method, path, kw))
        if path == "/search":
            return {"results": [
                {"work_id": "ol:1", "title": "Momo", "author": "Michael Ende", "year": 1973, "cover_url": "c",
                 "content_kind": "book", "available_book_types": ["audiobook", "ebook"]},
                {"work_id": "cv:9", "title": "Comic", "content_kind": "comic", "available_book_types": ["comicbook"]},
            ]}
        if path == "/requests" and method == "GET":
            return store
        if path == "/requests" and method == "POST":
            return {"requests": [_req(3, kw["json"]["username"], kw["json"]["title"], "pending", kw["json"]["book_type"])],
                    "queued": False, "warnings": [], "errors": []}
        if path.startswith("/requests/") and method == "GET":
            rid = int(path.split("/")[2])
            return next(r for r in store["requests"] if r["id"] == rid)
        if path.startswith("/requests/") and method == "DELETE":
            rid = int(path.split("/")[2])
            return {**next(r for r in store["requests"] if r["id"] == rid), "status": "failed"}
        raise AssertionError(path)

    monkeypatch.setattr(books, "_shelfarr", fake)
    books._search_cache.clear()
    yield calls
    books._search_cache.clear()


def test_search_returns_only_books_with_types(client, shelf):
    a = _auth(client, "book_a")
    data = client.get("/api/books/search?q=Momo", headers=a).json()
    assert data["status"] == "ok"
    assert [i["title"] for i in data["items"]] == ["Momo"]
    assert data["items"][0]["book_types"] == ["audiobook", "ebook"]


def test_requests_only_own(client, shelf):
    a = _auth(client, "book_a")
    items = client.get("/api/books/requests", headers=a).json()["items"]
    assert [i["title"] for i in items] == ["Momo"]
    assert items[0]["status_label"] == "Wird gesucht"


def test_create_request_as_own_user_in_german(client, shelf):
    b = _auth(client, "book_b")
    resp = client.post("/api/books/requests", headers=b,
                       json={"work_id": "ol:1", "book_type": "audiobook", "title": "Momo", "author": "Michael Ende"})
    assert resp.status_code == 201
    sent = [c for c in shelf if c[0] == "POST"][0][2]["json"]
    assert sent["username"] == "book_b"
    assert sent["language"] == "de"
    assert sent["book_type"] == "audiobook"
    assert resp.json()["items"][0]["status"] == "pending"


def test_user_map_overrides_username(client, shelf, monkeypatch):
    monkeypatch.setattr(settings, "shelfarr_user_map", "book_c=ben_shelf")
    c = _auth(client, "book_c")
    client.post("/api/books/requests", headers=c, json={"work_id": "ol:1", "book_type": "ebook", "title": "Momo"})
    assert [x for x in shelf if x[0] == "POST"][0][2]["json"]["username"] == "ben_shelf"


def test_cancel_foreign_request_404_own_ok(client, shelf):
    a = _auth(client, "book_a")
    assert client.delete("/api/books/requests/2", headers=a).status_code == 404
    assert not [c for c in shelf if c[0] == "DELETE"]
    assert client.delete("/api/books/requests/1", headers=a).status_code == 200


def test_not_configured_is_status_not_exception(client, monkeypatch):
    monkeypatch.setattr(settings, "shelfarr_url", None)
    a = _auth(client, "book_a")
    data = client.get("/api/books/search?q=x", headers=a).json()
    assert data == {"status": "not_configured", "error": "Shelfarr ist nicht eingerichtet", "items": []}


def test_unreachable_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(settings, "shelfarr_url", "http://shelfarr.test")
    monkeypatch.setattr(settings, "shelfarr_token", "tok")

    async def down(*a, **k):
        raise books.ShelfarrError("Shelfarr nicht erreichbar: timeout")

    monkeypatch.setattr(books, "_shelfarr", down)
    a = _auth(client, "book_a")
    data = client.get("/api/books/requests", headers=a).json()
    assert data["status"] == "unavailable" and "timeout" in data["error"]


def test_short_queries_never_reach_shelfarr(client, shelf):
    """Kurze Suchen beim Tippen: OpenLibrary lehnt sie ab (422), Shelfarr sperrt die Quelle dann minutenlang."""
    calls = shelf
    a = _auth(client, "book_short")
    before = len(calls)
    for q in ("k", "ke", "  ke  "):
        data = client.get(f"/api/books/search?q={q}", headers=a).json()
        assert data == {"status": "ok", "error": None, "items": []}
    assert len(calls) == before


def test_same_search_hits_shelfarr_once(client, shelf):
    """Jede Shelfarr-Suche fragt Google Books; Wiederholungen und Artwechsel kommen aus dem Cache."""
    a = _auth(client, "book_cache")
    for q, kind in [("Momo", None), ("  momo ", None), ("MOMO", "ebook"), ("Momo", "audiobook")]:
        url = f"/api/books/search?q={q}" + (f"&book_type={kind}" if kind else "")
        assert [i["title"] for i in client.get(url, headers=a).json()["items"]] == ["Momo"]
    assert len([c for c in shelf if c[1] == "/search"]) == 1
    assert [c[2]["params"]["q"] for c in shelf if c[1] == "/search"] == ["Momo"]


def test_failed_search_is_not_cached(client, shelf, monkeypatch):
    a = _auth(client, "book_cache2")
    good = books._shelfarr
    fails = {"n": 0}

    async def flaky(method, path, **kw):
        if path == "/search" and fails["n"] == 0:
            fails["n"] += 1
            raise books.ShelfarrError("Google Books: Kontingent erschöpft")
        return await good(method, path, **kw)

    monkeypatch.setattr(books, "_shelfarr", flaky)
    assert client.get("/api/books/search?q=Momo", headers=a).json()["status"] == "unavailable"
    assert client.get("/api/books/search?q=Momo", headers=a).json()["items"][0]["title"] == "Momo"
