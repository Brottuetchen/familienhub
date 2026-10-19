"""GitHub access of the plugin installer.

Only three hosts are ever contacted, always over https, never following a redirect, with timeouts and
size limits:

- ``api.github.com``: resolve a branch, tag or commit to a commit SHA,
- ``raw.githubusercontent.com``: the manifest at exactly that SHA,
- ``codeload.github.com``: the source tarball of exactly that SHA.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple
from urllib.parse import urlsplit

import httpx

API_HOST = "api.github.com"
RAW_HOST = "raw.githubusercontent.com"
CODELOAD_HOST = "codeload.github.com"
ALLOWED_HOSTS = frozenset({API_HOST, RAW_HOST, CODELOAD_HOST})

MAX_TARBALL_BYTES = 10 * 1024 * 1024
TIMEOUT = httpx.Timeout(15.0, read=30.0)

OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
SEGMENT_RE = re.compile(r"^[A-Za-z0-9._+-]{1,100}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class GitHubError(ValueError):
    """A problem with the GitHub side; the message is German and meant for the admin."""


class NotFound(GitHubError):
    """GitHub answered 404 or 422 (no such repository, ref or file)."""


@dataclass(frozen=True)
class RepoRef:
    owner: str
    repo: str
    rest: Tuple[str, ...]  # path segments after /tree/: ref (possibly with slashes) followed by a folder

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}"


def parse_repo_url(url: str) -> RepoRef:
    """``https://github.com/<owner>/<repo>[/tree/<ref>[/<path>]]`` → parts. Nothing else is accepted."""
    parts = urlsplit((url or "").strip())
    if parts.scheme != "https" or parts.username or parts.password or parts.port or parts.query or parts.fragment:
        raise GitHubError("Nur https-Adressen von GitHub ohne Zusätze")
    if (parts.hostname or "").lower() not in ("github.com", "www.github.com"):
        raise GitHubError("Nur Plugins von GitHub (github.com)")
    segs = [s for s in parts.path.split("/") if s]
    if len(segs) < 2:
        raise GitHubError("GitHub-Adresse braucht Besitzer und Repository")
    owner, repo = segs[0], segs[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not OWNER_RE.match(owner) or not REPO_RE.match(repo) or repo in (".", ".."):
        raise GitHubError("Ungültige GitHub-Adresse")
    rest: List[str] = segs[2:]
    if rest:
        if rest[0] != "tree" or len(rest) < 2:
            raise GitHubError("Adresse: https://github.com/<Besitzer>/<Repository> (optional /tree/<Branch>/<Ordner>)")
        rest = rest[1:]
        if any(not SEGMENT_RE.match(s) or s in (".", "..") for s in rest):
            raise GitHubError("Ungültiger Pfad")
    return RepoRef(owner, repo, tuple(rest))


def _check(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https" or (parts.hostname or "").lower() not in ALLOWED_HOSTS or parts.port:
        raise GitHubError("Zugriff auf diese Adresse ist nicht erlaubt")


def _transport() -> Optional[httpx.AsyncBaseTransport]:
    return None  # tests may replace this; respx works without it


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False, transport=_transport(),
                             headers={"User-Agent": "familienhub-plugin-installer"})


def _status_error(code: int) -> GitHubError:
    if code in (301, 302, 307, 308):
        return GitHubError("GitHub leitet um (Repository umbenannt?). Bitte die aktuelle Adresse verwenden")
    if code in (403, 429):
        return GitHubError("GitHub begrenzt gerade die Anfragen. Bitte später erneut versuchen")
    if code in (404, 422):
        return NotFound("Nicht gefunden (Repository privat oder Adresse falsch?)")
    return GitHubError(f"GitHub antwortet mit HTTP {code}")


async def _read(http: httpx.AsyncClient, url: str, limit: int, headers: Optional[dict] = None) -> bytes:
    """GET on an allowed host, 200 only, body at most ``limit`` bytes."""
    _check(url)
    chunks: List[bytes] = []
    size = 0
    try:
        async with http.stream("GET", url, headers=headers) as resp:
            if resp.status_code != 200:
                raise _status_error(resp.status_code)
            async for chunk in resp.aiter_bytes():
                size += len(chunk)
                if size > limit:
                    raise GitHubError("Antwort von GitHub ist zu groß")
                chunks.append(chunk)
    except httpx.TimeoutException as exc:
        raise GitHubError("GitHub antwortet nicht (Zeitüberschreitung)") from exc
    except httpx.HTTPError as exc:
        raise GitHubError("GitHub nicht erreichbar") from exc
    return b"".join(chunks)


async def resolve_sha(ref: RepoRef) -> Tuple[str, str]:
    """(sha, folder) of the linked ref. Without a ref the default branch counts.

    A branch name may contain slashes (``feature/x``), so ``tree/feature/x/sub`` is tried as ref ``feature``,
    then ``feature/x`` … (at most five tries); the remainder is the folder inside the repository.
    """
    base = f"https://{API_HOST}/repos/{ref.owner}/{ref.repo}/commits"
    async with client() as http:
        if not ref.rest:
            return await _commit(http, f"{base}/HEAD"), ""
        for i in range(1, min(len(ref.rest), 5) + 1):
            try:
                return await _commit(http, f"{base}/{'/'.join(ref.rest[:i])}"), "/".join(ref.rest[i:])
            except NotFound:
                continue
        raise GitHubError("Branch, Tag oder Commit nicht gefunden")


async def _commit(http: httpx.AsyncClient, url: str) -> str:
    # The "sha" media type answers with the bare commit id instead of the whole commit
    body = await _read(http, url, 256 * 1024, {"Accept": "application/vnd.github.sha"})
    text = body.decode("utf-8", "replace").strip()
    if text.startswith("{"):
        import json

        try:
            text = str(json.loads(text).get("sha", ""))
        except (ValueError, AttributeError):
            text = ""
    if not SHA_RE.match(text):
        raise GitHubError("GitHub liefert keine gültige Commit-Kennung")
    return text


async def fetch_manifest_bytes(ref: RepoRef, sha: str, folder: str, filename: str) -> bytes:
    """The manifest file at exactly this commit (at most 64 KB plus one byte, so oversize is detectable)."""
    if not SHA_RE.match(sha):
        raise GitHubError("Ungültige Commit-Kennung")
    path = "/".join(p for p in (folder, filename) if p)
    url = f"https://{RAW_HOST}/{ref.owner}/{ref.repo}/{sha}/{path}"
    async with client() as http:
        try:
            return await _read(http, url, 64 * 1024 + 1)
        except NotFound as exc:
            raise GitHubError(f"Im Repository liegt keine {filename}") from exc
        except GitHubError as exc:
            if "zu groß" in str(exc):
                raise GitHubError(f"{filename} ist größer als 64 KB") from exc
            raise


async def download_tarball(owner: str, repo: str, sha: str) -> bytes:
    """Source tarball of exactly this commit, at most 10 MB."""
    if not SHA_RE.match(sha) or not OWNER_RE.match(owner) or not REPO_RE.match(repo):
        raise GitHubError("Ungültige Commit-Kennung")
    url = f"https://{CODELOAD_HOST}/{owner}/{repo}/tar.gz/{sha}"
    async with client() as http:
        try:
            return await _read(http, url, MAX_TARBALL_BYTES)
        except GitHubError as exc:
            if "zu groß" in str(exc):
                raise GitHubError("Das Repository ist größer als 10 MB") from exc
            raise
