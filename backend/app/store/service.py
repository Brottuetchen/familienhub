"""Store sources, index cache, merged listing, screenshot proxy (``docs/store.md``).

Rules: only https, only ``raw.githubusercontent.com`` (plus the host of the operator's own ``STORE_INDEX_URL``),
no redirects, timeouts, size limits. A source that cannot be reached or parsed yields an empty list plus a status,
never an exception into the UI. The official source (``STORE_INDEX_URL``) is ``verified``; sources an admin added
are not.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import httpx
from sqlalchemy.orm import Session

from app import __version__
from app.config import settings
from app.core.logging_config import get_logger
from app.models.installed_plugin import InstalledPlugin
from app.models.store_source import StoreSource
from app.models.theme import Theme
from app.plugins import github
from app.plugins.registry import plugin_registry
from app.routers import themes as themes_router
from app.store import index as idx

logger = get_logger("store")

OFFICIAL = "official"
MAX_CUSTOM_SOURCES = 10
MAX_SCREENSHOT_BYTES = 2 * 1024 * 1024
SHOT_CACHE_ITEMS = 64
FAILURE_TTL = 30.0  # seconds a failed fetch is remembered, so an unreachable store is not hammered
IMAGE_MAGIC = ((b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"))


class FetchError(Exception):
    """A fetch failed; ``status`` is ``unreachable`` or ``invalid`` (not found, wrong format, too large)."""

    def __init__(self, status: str, reason: str):
        super().__init__(reason)
        self.status = status


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    index_url: str
    verified: bool
    db_id: Optional[int] = None
    repo_url: str = ""


@dataclass
class SourceData:
    status: str  # ok | unreachable | invalid
    name: str = ""
    entries: List[idx.Entry] = field(default_factory=list)
    skipped: List[Dict[str, str]] = field(default_factory=list)
    reason: str = ""
    stale: bool = False


_cache: Dict[str, Tuple[float, SourceData]] = {}
_shots: Dict[str, Tuple[float, bytes, str]] = {}


def clear_cache() -> None:
    _cache.clear()
    _shots.clear()


# --- Sources ---

def custom_index_url(repo_url: str) -> str:
    """``https://github.com/o/r[/tree/<branch>]`` → raw URL of its ``index.json`` (default branch: ``HEAD``)."""
    ref = github.parse_repo_url(repo_url)
    if len(ref.rest) > 1:
        raise github.GitHubError("Adresse: https://github.com/<Besitzer>/<Repository> (optional /tree/<Branch>)")
    branch = ref.rest[0] if ref.rest else "HEAD"
    return f"https://{github.RAW_HOST}/{ref.owner}/{ref.repo}/{branch}/index.json"


def normalise_repo_url(repo_url: str) -> str:
    ref = github.parse_repo_url(repo_url)
    custom_index_url(repo_url)  # at most a branch
    return ref.url + ("/tree/" + ref.rest[0] if ref.rest else "")


def sources(db: Session) -> List[Source]:
    out: List[Source] = []
    official = (settings.store_index_url or "").strip()
    if official:
        out.append(Source(OFFICIAL, "Familienhub", official, True))
    for row in db.query(StoreSource).order_by(StoreSource.id).all():
        try:
            url = custom_index_url(row.repo_url)
        except ValueError:
            logger.warning("Store source %s has an invalid address and is ignored", row.id)
            continue
        out.append(Source(f"custom-{row.id}", row.name or row.repo_url, url, False, row.id, row.repo_url))
    return out


# --- Fetching ---

async def _get(url: str, limit: int, hosts: frozenset) -> bytes:
    parts = urlsplit(url)
    if parts.scheme != "https" or (parts.hostname or "").lower() not in hosts or parts.port:
        raise FetchError("invalid", "address not allowed")
    chunks: List[bytes] = []
    size = 0
    try:
        async with github.client() as http:
            async with http.stream("GET", url) as resp:
                if resp.status_code != 200:
                    raise FetchError("invalid" if resp.status_code in (404, 410) else "unreachable",
                                     f"HTTP {resp.status_code}")
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > limit:
                        raise FetchError("invalid", "response too large")
                    chunks.append(chunk)
    except httpx.HTTPError as exc:
        raise FetchError("unreachable", exc.__class__.__name__) from exc
    return b"".join(chunks)


async def fetch_index(source: Source) -> SourceData:
    try:
        body = await _get(source.index_url, idx.MAX_INDEX_BYTES, idx.hosts_for(source.index_url))
        parsed = idx.parse_index(body, source.index_url, idx.hosts_for(source.index_url))
    except FetchError as exc:
        return SourceData(exc.status, reason=str(exc))
    except idx.IndexError_ as exc:
        return SourceData("invalid", reason=str(exc))
    return SourceData("ok", parsed.name, parsed.entries, parsed.skipped)


async def load(source: Source, refresh: bool = False) -> SourceData:
    """The source's index, from the cache while fresh. A failed refresh falls back to the last good copy."""
    now = time.monotonic()
    cached = _cache.get(source.index_url)
    if cached and not refresh:
        ttl = settings.store_cache_seconds if cached[1].status == "ok" else FAILURE_TTL
        if now - cached[0] < ttl:
            return cached[1]
    data = await fetch_index(source)
    if data.status != "ok":
        logger.warning("Store source %s: %s (%s)", source.key, data.status, data.reason)
        if cached and cached[1].status == "ok":
            data = SourceData("ok", cached[1].name, cached[1].entries, cached[1].skipped, data.reason, stale=True)
            _cache[source.index_url] = (cached[0], data)
            return data
    _cache[source.index_url] = (now, data)
    return data


async def load_all(db: Session, refresh: bool = False) -> List[Tuple[Source, SourceData]]:
    srcs = sources(db)
    results = await asyncio.gather(*(load(s, refresh) for s in srcs))
    return list(zip(srcs, results))


async def find(db: Session, source_key: str, kind: str, entry_id: str) -> Tuple[Source, idx.Entry]:
    """The entry as the current index lists it; ``LookupError`` if source or entry is gone."""
    for src in sources(db):
        if src.key == source_key:
            data = await load(src)
            for entry in data.entries:
                if entry.type == kind and entry.id == entry_id:
                    return src, entry
    raise LookupError(f"{source_key}/{kind}/{entry_id}")


# --- Merged listing ---

def _same_repo(a: str, b: str) -> bool:
    try:
        return github.parse_repo_url(a).url.lower() == github.parse_repo_url(b).url.lower()
    except ValueError:
        return False


def install_state(entry: idx.Entry, plugins: Dict[str, InstalledPlugin], themes: Dict[str, Theme],
                  builtin_names: set, theme_names: set) -> Tuple[str, Optional[str]]:
    """(state, installed version): ``available`` | ``installed`` | ``update`` | ``conflict``."""
    if entry.type == "plugin":
        row = plugins.get(entry.id)
        if row is None:
            return ("conflict", None) if plugin_registry.get(entry.id) is not None else ("available", None)
        if not _same_repo(row.repo_url, entry.repo):
            return "conflict", row.version
        return ("installed" if row.sha == entry.sha else "update"), row.version
    name = idx.pick(entry.name, "de").lower()
    row = themes.get(entry.id)
    if row is not None:
        return ("installed" if row.store_sha == entry.sha else "update"), row.store_version
    if name in builtin_names or idx.pick(entry.name, "en").lower() in builtin_names:
        return "installed", None
    if name in theme_names:
        return "conflict", None
    return "available", None


def shot_path(source_key: str, entry: idx.Entry, n: int) -> str:
    return f"/api/admin/store/screenshot/{source_key}/{entry.type}/{entry.id}/{n}"


def item_view(source: Source, entry: idx.Entry, lang: str, state: str, installed_version: Optional[str]) -> Dict[str, Any]:
    return {
        "source": source.key,
        "verified": source.verified,
        "type": entry.type,
        "id": entry.id,
        "name": idx.pick(entry.name, lang),
        "summary": idx.pick(entry.summary, lang),
        "description": idx.pick(entry.description, lang),
        "author": entry.author,
        "repo": entry.repo,
        "path": entry.path,
        "version": entry.version,
        "sha": entry.sha,
        "short_sha": entry.sha[:7],
        "tags": list(entry.tags),
        "min_hub_version": entry.min_hub_version,
        "compatible": idx.optional_hub_ok(entry, __version__),
        "screenshots": [shot_path(source.key, entry, i) for i in range(len(entry.screenshots))],
        "state": state,
        "installed_version": installed_version,
    }


def source_view(source: Source, data: SourceData) -> Dict[str, Any]:
    return {
        "id": source.key,
        "name": data.name or source.name,
        "url": source.repo_url or source.index_url,
        "verified": source.verified,
        "removable": source.db_id is not None,
        "status": data.status,
        "stale": data.stale,
        "entries": len(data.entries),
        "skipped": data.skipped[:20],
    }


async def listing(db: Session, lang: str, refresh: bool = False) -> Dict[str, Any]:
    loaded = await load_all(db, refresh)
    plugins = {r.id: r for r in db.query(InstalledPlugin).all()}
    all_themes = db.query(Theme).all()
    themes = {t.store_id: t for t in all_themes if t.store_id}
    theme_names = {t.name.lower() for t in all_themes}
    builtin_names = {t["name"].lower() for t in themes_router.builtin_themes()}
    items: List[Dict[str, Any]] = []
    for src, data in loaded:
        for entry in data.entries:
            state, version = install_state(entry, plugins, themes, builtin_names, theme_names)
            items.append(item_view(src, entry, lang, state, version))
    items.sort(key=lambda i: (not i["verified"], i["name"].lower()))
    return {
        "installer_enabled": settings.plugin_install_enabled,
        "sources": [source_view(s, d) for s, d in loaded],
        "items": items,
    }


# --- Screenshots ---

def _sniff(body: bytes) -> Optional[str]:
    for magic, mime in IMAGE_MAGIC:
        if body.startswith(magic):
            return mime
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "image/webp"
    return None  # SVG and anything else is refused


async def screenshot(db: Session, source_key: str, kind: str, entry_id: str, n: int) -> Tuple[bytes, str]:
    """(bytes, content type) of one screenshot of an entry that is listed right now. ``LookupError`` if none."""
    src, entry = await find(db, source_key, kind, entry_id)
    if not 0 <= n < len(entry.screenshots):
        raise LookupError("screenshot")
    url = entry.screenshots[n]
    now = time.monotonic()
    hit = _shots.get(url)
    if hit and now - hit[0] < settings.store_cache_seconds:
        return hit[1], hit[2]
    try:
        body = await _get(url, MAX_SCREENSHOT_BYTES, idx.hosts_for(src.index_url))
    except FetchError as exc:
        raise LookupError("screenshot") from exc
    mime = _sniff(body)
    if mime is None:
        raise LookupError("screenshot")
    if len(_shots) >= SHOT_CACHE_ITEMS:
        _shots.pop(min(_shots, key=lambda k: _shots[k][0]))
    _shots[url] = (now, body, mime)
    return body, mime


def theme_url(entry: idx.Entry) -> str:
    folder = f"{entry.path}/" if entry.path else ""
    return f"https://{github.RAW_HOST}/{entry.owner}/{entry.repo_name}/{entry.sha}/{folder}theme.json"
