"""``index.json`` of a store source: parsing and strict validation (format in ``docs/store.md``).

An index is ``{"version": 1, "name": "...", "entries": [...]}``. A wrong ``version`` or a malformed top level
rejects the whole index (``IndexError_``); a malformed *entry* is skipped with a logged reason, so one bad pull
request in a store repository never hides the other entries.

Messages here are developer-facing (logs, ``skipped`` list) and therefore English.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple
from urllib.parse import urlsplit

from app.core.logging_config import get_logger
from app.plugins import github
from app.plugins.manifest import ID_RE, VERSION_RE, is_reserved_id

logger = get_logger("store.index")

INDEX_VERSION = 1
MAX_INDEX_BYTES = 1024 * 1024
MAX_ENTRIES = 500
MAX_SCREENSHOTS = 8
TYPES = ("theme", "plugin")
LANGUAGES = ("de", "en")

THEME_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{1,40}$")
PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
TOP_KEYS = {"version", "name", "entries"}
ENTRY_KEYS = {"type", "id", "name", "summary", "description", "author", "repo", "path", "sha", "version",
              "screenshots", "tags", "min_hub_version"}
REQUIRED_ENTRY_KEYS = ("type", "id", "name", "summary", "author", "repo", "sha", "version")


class IndexError_(ValueError):
    """The index as a whole is unusable (not JSON, too large, unknown version, wrong shape)."""


class EntryError(ValueError):
    """One entry is invalid; the index stays usable."""


@dataclass(frozen=True)
class Entry:
    type: str
    id: str
    name: Dict[str, str]
    summary: Dict[str, str]
    description: Dict[str, str]
    author: str
    repo: str  # https://github.com/<owner>/<repo>
    owner: str
    repo_name: str
    path: str  # folder inside the repository ("" = root)
    sha: str
    version: str
    screenshots: Tuple[str, ...]  # absolute URLs on allowed hosts
    tags: Tuple[str, ...]
    min_hub_version: str


@dataclass
class ParsedIndex:
    name: str = ""
    entries: List[Entry] = field(default_factory=list)
    skipped: List[Dict[str, str]] = field(default_factory=list)  # {"id": ..., "reason": ...}


def _text(value: Any, field_name: str, max_len: int, required: bool = True) -> Dict[str, str]:
    """A string or ``{"de": ..., "en": ...}`` → always a dict (a plain string counts for both languages)."""
    if value is None or value == "":
        if required:
            raise EntryError(f"{field_name} is missing")
        return {}
    if isinstance(value, str):
        value = {"de": value, "en": value}
    if not isinstance(value, dict) or not value or set(value) - set(LANGUAGES):
        raise EntryError(f"{field_name} must be a string or an object with only de and en")
    out: Dict[str, str] = {}
    for lang, text in value.items():
        if not isinstance(text, str) or not text.strip() or len(text.strip()) > max_len:
            raise EntryError(f"{field_name}.{lang} is empty or longer than {max_len} characters")
        out[lang] = text.strip()
    return out


def pick(texts: Dict[str, str], lang: str) -> str:
    """Text in ``lang``; falls back to the other language."""
    return texts.get(lang) or texts.get("en") or texts.get("de") or ""


def _folder(value: Any) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str) or len(value) > 200:
        raise EntryError("path must be a string")
    parts = value.strip("/").split("/")
    if any(not PATH_SEGMENT_RE.match(p) or p in (".", "..") for p in parts):
        raise EntryError("path contains invalid segments")
    return "/".join(parts)


def resolve_screenshot(value: Any, base_url: str, allowed_hosts: frozenset) -> str:
    """Relative path (resolved against the folder of ``index.json``) or https URL on an allowed host."""
    if not isinstance(value, str) or not value or len(value) > 300:
        raise EntryError("screenshot must be a non-empty string")
    if not value.lower().endswith(IMAGE_EXTENSIONS):
        raise EntryError("screenshot must be a .png, .jpg or .webp file")
    if "://" in value:
        parts = urlsplit(value)
        if (parts.scheme != "https" or parts.username or parts.password or parts.port or parts.query
                or parts.fragment or (parts.hostname or "").lower() not in allowed_hosts):
            raise EntryError("screenshot URL is not an https URL on an allowed host")
        return value
    segments = value.split("/")
    if any(not PATH_SEGMENT_RE.match(s) or s in (".", "..") for s in segments):
        raise EntryError("screenshot path must be relative and without .. segments")
    return base_url.rsplit("/", 1)[0] + "/" + value


def parse_entry(raw: Any, base_url: str, allowed_hosts: frozenset) -> Entry:
    if not isinstance(raw, dict):
        raise EntryError("entry must be an object")
    unknown = sorted(set(raw) - ENTRY_KEYS)
    if unknown:
        raise EntryError(f"unknown fields: {', '.join(unknown)}")
    for key in REQUIRED_ENTRY_KEYS:
        if raw.get(key) in (None, ""):
            raise EntryError(f"{key} is missing")
    kind = raw["type"]
    if kind not in TYPES:
        raise EntryError("type must be theme or plugin")
    entry_id = raw["id"]
    if not isinstance(entry_id, str) or not (ID_RE if kind == "plugin" else THEME_ID_RE).match(entry_id):
        raise EntryError("id is not valid for this type")
    if kind == "plugin" and is_reserved_id(entry_id):
        raise EntryError("plugin id is reserved")
    try:
        ref = github.parse_repo_url(raw["repo"]) if isinstance(raw["repo"], str) else None
    except github.GitHubError as exc:
        raise EntryError("repo must be https://github.com/<owner>/<repo>") from exc
    if ref is None or ref.rest:
        raise EntryError("repo must be https://github.com/<owner>/<repo> (use path for a folder)")
    sha = raw["sha"]
    if not isinstance(sha, str) or not github.SHA_RE.match(sha):
        raise EntryError("sha must be a full lowercase 40-character commit id")
    version = raw["version"]
    if not isinstance(version, str) or not VERSION_RE.match(version):
        raise EntryError("version is not valid")
    author = raw["author"]
    if not isinstance(author, str) or not author.strip() or len(author.strip()) > 60:
        raise EntryError("author is empty or longer than 60 characters")
    min_hub = raw.get("min_hub_version") or ""
    if not isinstance(min_hub, str) or (min_hub and not VERSION_RE.match(min_hub)):
        raise EntryError("min_hub_version is not valid")
    shots = raw.get("screenshots") or []
    if not isinstance(shots, list) or len(shots) > MAX_SCREENSHOTS:
        raise EntryError(f"screenshots must be a list of at most {MAX_SCREENSHOTS}")
    tags = raw.get("tags") or []
    if (not isinstance(tags, list) or len(tags) > 8
            or any(not isinstance(t, str) or not t.strip() or len(t.strip()) > 24 for t in tags)):
        raise EntryError("tags must be at most 8 short strings")
    summary = _text(raw["summary"], "summary", 140)
    return Entry(
        type=kind, id=entry_id, name=_text(raw["name"], "name", 60), summary=summary,
        description=_text(raw.get("description"), "description", 2000, required=False) or summary,
        author=author.strip(), repo=ref.url, owner=ref.owner, repo_name=ref.repo, path=_folder(raw.get("path")),
        sha=sha, version=version,
        screenshots=tuple(resolve_screenshot(s, base_url, allowed_hosts) for s in shots),
        tags=tuple(t.strip() for t in tags), min_hub_version=min_hub,
    )


def parse_index(body: bytes, base_url: str, allowed_hosts: frozenset) -> ParsedIndex:
    """Entries that validate, plus the reasons for the ones that do not. Raises ``IndexError_`` for a bad index."""
    if len(body) > MAX_INDEX_BYTES:
        raise IndexError_("index.json is larger than 1 MB")
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise IndexError_("index.json is not valid JSON") from exc
    if not isinstance(data, dict) or set(data) - TOP_KEYS:
        raise IndexError_("index.json must be an object with version, name and entries")
    if data.get("version") != INDEX_VERSION or isinstance(data.get("version"), bool):
        raise IndexError_(f"unsupported index version {data.get('version')!r} (this hub reads version {INDEX_VERSION})")
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise IndexError_("entries must be a list")
    name = data.get("name") or ""
    result = ParsedIndex(name=name.strip()[:80] if isinstance(name, str) else "")
    seen: set = set()
    for i, raw in enumerate(entries[:MAX_ENTRIES]):
        label = raw.get("id") if isinstance(raw, dict) and isinstance(raw.get("id"), str) else f"#{i}"
        try:
            entry = parse_entry(raw, base_url, allowed_hosts)
            if (entry.type, entry.id) in seen:
                raise EntryError("duplicate entry")
            seen.add((entry.type, entry.id))
            result.entries.append(entry)
        except EntryError as exc:
            logger.warning("Store index %s: entry %s skipped: %s", base_url, label, exc)
            result.skipped.append({"id": str(label)[:60], "reason": str(exc)})
    if len(entries) > MAX_ENTRIES:
        result.skipped.append({"id": "", "reason": f"only the first {MAX_ENTRIES} entries are read"})
    return result


def hosts_for(index_url: str) -> frozenset:
    host = (urlsplit(index_url).hostname or "").lower()
    return frozenset({github.RAW_HOST, host} - {""})


def optional_hub_ok(entry: Entry, hub_version: str) -> bool:
    from app.plugins.manifest import hub_version_ok

    return not entry.min_hub_version or hub_version_ok(entry.min_hub_version, hub_version)


__all__ = ["Entry", "EntryError", "IndexError_", "ParsedIndex", "parse_index", "parse_entry", "pick", "hosts_for",
           "optional_hub_ok"]
