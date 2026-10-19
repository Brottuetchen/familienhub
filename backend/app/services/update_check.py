"""Notice about a newer Familienhub release (Administration).

The hub asks the GitHub releases API of the configured repository (``UPDATE_CHECK_REPO``), at most a few
times a day; the answer is cached in memory, failures too (so an unreachable GitHub is not hammered).
Pre-releases only count when the running version is a pre-release itself. Every failure ends in a
status, never in an exception. Switch off with ``UPDATE_CHECK=false``.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

from app import __version__
from app.config import settings
from app.core.logging_config import get_logger
from app.services.backup import is_prerelease, parse_version, truthy

logger = get_logger("service.update_check")

OK_TTL = 6 * 3600  # a few checks per day at most
FAIL_TTL = 30 * 60
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
API = "https://api.github.com/repos/{repo}/releases?per_page=30"
UPDATE_COMMAND = "docker compose pull && docker compose up -d"

_cache: Dict[str, Any] = {}  # repo -> (expires_monotonic, checked_at_iso, release|None, error|None)


def enabled() -> bool:
    return truthy(settings.update_check)


def repo() -> str:
    return (settings.update_check_repo or "").strip()


def reset() -> None:
    _cache.clear()


def pick_release(releases: Any, current: str) -> Optional[Dict[str, Any]]:
    """Newest release newer than ``current`` (pre-releases only for pre-release users), or None."""
    if not isinstance(releases, list):
        return None
    allow_pre = is_prerelease(current)
    ours = parse_version(current)
    best, best_key = None, None
    for r in releases:
        if not isinstance(r, dict) or r.get("draft"):
            continue
        key = parse_version(str(r.get("tag_name") or ""))
        if key is None:
            continue
        if (r.get("prerelease") or key[3] == 0) and not allow_pre:
            continue
        if best_key is None or key > best_key:
            best, best_key = r, key
    if best is None or ours is None or best_key <= ours:
        return None
    return best


async def _fetch(repo_name: str) -> Any:
    async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
        r = await client.get(API.format(repo=repo_name), headers={
            "Accept": "application/vnd.github+json", "User-Agent": "familienhub-update-check",
            "X-GitHub-Api-Version": "2022-11-28"})
    r.raise_for_status()
    return r.json()


def _command(tag: str, prerelease: bool) -> str:
    version = tag.lstrip("v")
    if prerelease:  # the default tag :latest never points at a pre-release
        return f"FAMILIENHUB_VERSION={version} docker compose pull && FAMILIENHUB_VERSION={version} docker compose up -d"
    return UPDATE_COMMAND


async def status() -> Dict[str, Any]:
    """Result for the admin panel (cached)."""
    base = {"enabled": enabled(), "repo": repo(), "current": __version__, "available": False, "latest": None,
            "url": None, "name": None, "published_at": None, "prerelease": False, "docker_command": UPDATE_COMMAND,
            "checked_at": None, "status": "off"}
    if not base["enabled"]:
        return base
    if parse_version(__version__) is None:
        return {**base, "status": "unknown_version"}  # development build: nothing to compare
    if not REPO_RE.match(base["repo"]):
        return {**base, "status": "bad_repo"}
    now = time.monotonic()
    hit = _cache.get(base["repo"])
    if hit and hit[0] > now:
        _, checked_at, release, error = hit
    else:
        checked_at, release, error = datetime.now(timezone.utc).isoformat(), None, None
        try:
            release = pick_release(await _fetch(base["repo"]), __version__)
        except (httpx.HTTPError, ValueError) as exc:
            error = type(exc).__name__
            logger.warning("update check failed: %s", error)
        _cache[base["repo"]] = (now + (OK_TTL if error is None else FAIL_TTL), checked_at, release, error)
    out = {**base, "checked_at": checked_at, "status": "unavailable" if error else "ok"}
    if release:
        tag = str(release.get("tag_name"))
        url = str(release.get("html_url") or "")
        if not url.startswith("https://github.com/"):
            url = f"https://github.com/{base['repo']}/releases/tag/{tag}"
        pre = bool(release.get("prerelease"))
        out.update(available=True, latest=tag.lstrip("v"), url=url, name=release.get("name") or tag,
                   published_at=release.get("published_at"), prerelease=pre, docker_command=_command(tag, pre))
    return out
