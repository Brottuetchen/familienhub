"""Book discovery: shelves of works that exist in German, from Open Library, requestable via Shelfarr."""

import httpx
import pytest
import respx

from app.config import settings

OL = "https://openlibrary.org/search.json"
DOCS = {"docs": [
    {"key": "/works/OL21745884W", "title": "Project Hail Mary", "author_name": ["Andy Weir"], "first_publish_year": 2021,
     "cover_i": 1, "editions": {"docs": [{"title": "Der Astronaut", "language": ["ger"], "cover_i": 42}]}},
    {"key": "/works/OL1W", "title": "Momo", "author_name": ["Michael Ende"], "first_publish_year": 1973,
     "editions": {"docs": [{"title": "Momo", "language": ["ger"]}]}},
    {"key": "/books/OL9M", "title": "Kein Werk"},
]}


@pytest.fixture
def shelfarr(monkeypatch):
    from app.services import book_discover

    monkeypatch.setattr(settings, "shelfarr_url", "http://shelfarr.test")
    monkeypatch.setattr(settings, "shelfarr_token", "t")
    book_discover.clear_cache()
    yield
    book_discover.clear_cache()


def test_shelf_items_have_german_title_cover_and_work_id(client, auth, shelfarr):
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        route = http.get(OL).mock(return_value=httpx.Response(200, json=DOCS))
        r = client.get("/api/books/discover", params={"shelf": "popular"}, headers=auth).json()
    assert r["status"] == "ok" and "crime" in r["shelves"]
    first = r["items"][0]
    assert first == {"work_id": "openlibrary:OL21745884W", "title": "Der Astronaut", "original_title": "Project Hail Mary",
                     "author": "Andy Weir", "year": 2021, "cover_url": "https://covers.openlibrary.org/b/id/42-M.jpg",
                     "book_types": []}
    assert r["items"][1]["original_title"] is None and r["items"][1]["cover_url"] is None
    assert len(r["items"]) == 2  # editions without a work key are skipped
    params = route.calls.last.request.url.params
    assert "language:ger" in params["q"] and params["sort"] == "readinglog" and params["lang"] == "de"


def test_shelves_are_cached_and_validated(client, auth, shelfarr):
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        route = http.get(OL).mock(return_value=httpx.Response(200, json=DOCS))
        client.get("/api/books/discover", params={"shelf": "fantasy"}, headers=auth)
        client.get("/api/books/discover", params={"shelf": "fantasy"}, headers=auth)
        assert route.call_count == 1
        assert "subject:fantasy" in route.calls.last.request.url.params["q"]
    assert client.get("/api/books/discover", params={"shelf": "nope"}, headers=auth).status_code == 422


def test_open_library_down_is_a_status(client, auth, shelfarr):
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        http.get(OL).mock(side_effect=httpx.ConnectError("down"))
        r = client.get("/api/books/discover", params={"shelf": "kids"}, headers=auth)
    assert r.status_code == 200 and r.json()["status"] == "unavailable" and r.json()["items"] == []


def test_without_shelfarr_not_configured(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "shelfarr_url", None)
    r = client.get("/api/books/discover", headers=auth).json()
    assert r["status"] == "not_configured" and r["items"] == []
