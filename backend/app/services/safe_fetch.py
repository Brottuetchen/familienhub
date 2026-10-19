"""Fetch a user-supplied URL with SSRF protection, a size limit and a timeout.

Only http(s) on the default ports. The host is resolved and every address must be public (no loopback,
private, link-local, multicast, reserved or unspecified ranges). Redirects are followed by hand so that
every hop is checked again.

Known limit: the check resolves the name itself and httpx resolves it again when connecting, so a DNS
rebinding attacker with a very short TTL could still win the race. For a family hub behind a login this
is accepted; the page content is never returned verbatim to the caller.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Tuple
from urllib.parse import urljoin, urlsplit

import httpx

MAX_BYTES = 2 * 1024 * 1024
TIMEOUT_SECONDS = 10
MAX_REDIRECTS = 4
ALLOWED_PORTS = {None, 80, 443}


class FetchError(Exception):
    """`reason` is one of: invalid_url, blocked, unreachable, too_large."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(detail or reason)
        self.reason = reason


def is_public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value.split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return bool(ip.is_global) and not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
                                       or ip.is_reserved or ip.is_unspecified)


async def resolve(host: str) -> list:
    """Addresses of a host. A separate function so tests can replace the DNS lookup."""
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})


async def check_url(url: str) -> str:
    """Raises FetchError unless the URL may be fetched."""
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        raise FetchError("invalid_url")
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme not in ("http", "https") or not host or parts.username or parts.password:
        raise FetchError("invalid_url")
    if port not in ALLOWED_PORTS or host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise FetchError("blocked")
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        try:
            addresses = await resolve(host)
        except OSError:
            raise FetchError("unreachable", "host not found")
    if not addresses or not all(is_public_ip(a) for a in addresses):
        raise FetchError("blocked", "address not public")
    return url.strip()


async def fetch_text(url: str, accept: str = "text/html,application/xhtml+xml") -> Tuple[str, str]:
    """Returns (final_url, body text). Raises FetchError."""
    current = await check_url(url)
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=False,
                                 headers={"Accept": accept, "User-Agent": "Familienhub-RecipeImport/1.0"}) as client:
        for _ in range(MAX_REDIRECTS + 1):
            try:
                async with client.stream("GET", current) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308):
                        target = resp.headers.get("location")
                        if not target:
                            raise FetchError("unreachable", "redirect without target")
                        current = await check_url(urljoin(current, target))
                        continue
                    if resp.status_code != 200:
                        raise FetchError("unreachable", f"HTTP {resp.status_code}")
                    ctype = resp.headers.get("content-type", "").lower()
                    if ctype and not any(t in ctype for t in ("html", "xml", "text/plain", "json")):
                        raise FetchError("unreachable", "not a web page")
                    chunks, size = [], 0
                    async for chunk in resp.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise FetchError("too_large")
                        chunks.append(chunk)
                    raw = b"".join(chunks)
                    encoding = resp.charset_encoding or "utf-8"
                    try:
                        return current, raw.decode(encoding, errors="replace")
                    except LookupError:
                        return current, raw.decode("utf-8", errors="replace")
            except httpx.HTTPError as exc:
                raise FetchError("unreachable", type(exc).__name__)
    raise FetchError("unreachable", "too many redirects")
