"""Book discovery ("Entdecken") from Open Library: popular and well-rated works that exist in German.

Open Library is free and official (https://openlibrary.org/developers/api). Shelfarr uses Open Library work ids
(``openlibrary:OL…W``), so every item can be requested directly. Titles and covers come from the German edition.
Bestseller lists (SPIEGEL, Audible, Thalia) have no public API and are not scraped.
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.logging_config import get_logger

logger = get_logger("service.book_discover")

OPENLIBRARY = "https://openlibrary.org/search.json"
COVERS = "https://covers.openlibrary.org/b/id/{}-M.jpg"
CACHE_SECONDS = 6 * 3600
FIELDS = "key,title,author_name,first_publish_year,cover_i,editions,editions.title,editions.language,editions.cover_i"


def _shelves() -> Dict[str, Tuple[str, str]]:
    recent = date.today().year - 2
    return {  # id → (query, sort)
        "popular": ("language:ger", "readinglog"),
        "new": (f"language:ger first_publish_year:[{recent} TO *]", "readinglog"),
        "top_rated": ("language:ger", "rating"),
        "crime": ('language:ger (subject:thriller OR subject:"detective and mystery stories" OR subject:kriminalroman)', "readinglog"),
        "fantasy": ("language:ger subject:fantasy", "readinglog"),
        "romance": ("language:ger subject:romance", "readinglog"),
        "kids": ('language:ger subject:"juvenile fiction"', "readinglog"),
    }


SHELVES = list(_shelves())
_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}


def clear_cache() -> None:
    _cache.clear()


def _item(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    key = str(doc.get("key") or "")
    if not key.startswith("/works/"):
        return None
    edition = next(iter((doc.get("editions") or {}).get("docs") or []), {}) or {}
    german = "ger" in (edition.get("language") or [])
    cover = (edition.get("cover_i") if german else None) or doc.get("cover_i")
    title = (edition.get("title") if german else None) or doc.get("title") or ""
    return {
        "work_id": "openlibrary:" + key.rsplit("/", 1)[-1],
        "title": title,
        "original_title": doc.get("title") if doc.get("title") != title else None,
        "author": (doc.get("author_name") or [None])[0],
        "year": doc.get("first_publish_year"),
        "cover_url": COVERS.format(cover) if cover else None,
        "book_types": [],  # unknown here; Shelfarr decides on request
    }


async def shelf(shelf_id: str) -> List[Dict[str, Any]]:
    """Items of a shelf (cached 6 h). Raises httpx.HTTPError if Open Library can't be reached."""
    hit = _cache.get(shelf_id)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    query, sort = _shelves()[shelf_id]
    async with httpx.AsyncClient(timeout=15, follow_redirects=True,
                                 headers={"User-Agent": "Familienhub (self-hosted family app)"}) as client:
        resp = await client.get(OPENLIBRARY, params={"q": query, "sort": sort, "lang": "de", "limit": 30, "fields": FIELDS})
        resp.raise_for_status()
    items = [i for i in (_item(d) for d in resp.json().get("docs", [])) if i and i["title"]]
    _cache[shelf_id] = (time.monotonic(), items)
    return items
