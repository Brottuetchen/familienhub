"""Signed, short-lived links to plugin pages (``Plugin.page``, ``docs/plugins.md``, "Plugin pages").

A page is opened in the browser, where the app's bearer token is not available, so the app asks the hub for a link
(``POST /api/plugin-pages/<plugin>/<page>/link``, logged in) and opens it. The link carries a token that is bound
to one person, one plugin and one page and expires after ``TOKEN_TTL`` seconds. It is an HMAC-SHA256 over the
payload, keyed with a key derived from the hub's secret key (separate from the JWT signing), compared in
constant time. The token is not encrypted: it holds only ids and the expiry.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Optional, Tuple

from app.config import settings

TOKEN_TTL = 15 * 60  # seconds
MAX_TOKEN_LENGTH = 300
_CONTEXT = b"familienhub/plugin-pages/v1"


def _key() -> bytes:
    return hmac.new((settings.secret_key or "").encode("utf-8"), _CONTEXT, hashlib.sha256).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: str) -> str:
    return _b64(hmac.new(_key(), payload.encode("ascii"), hashlib.sha256).digest())


def create_token(user_id: int, plugin_id: str, page_id: str, *, now: Optional[float] = None) -> str:
    exp = int((time.time() if now is None else now) + TOKEN_TTL)
    payload = _b64(json.dumps([user_id, plugin_id, page_id, exp], separators=(",", ":")).encode("utf-8"))
    return f"{payload}.{_sign(payload)}"


class Expired(Exception):
    """The signature is valid but the link has run out."""


def verify_token(token: str, *, now: Optional[float] = None) -> Optional[Tuple[int, str, str]]:
    """``(user_id, plugin_id, page_id)`` of a valid token, ``None`` for anything forged or malformed.
    Raises ``Expired`` for a genuine token that is past its expiry."""
    if not isinstance(token, str) or len(token) > MAX_TOKEN_LENGTH or token.count(".") != 1:
        return None
    payload, signature = token.split(".")
    try:
        ok = hmac.compare_digest(_sign(payload).encode("ascii"), signature.encode("ascii"))
    except (UnicodeEncodeError, ValueError):
        return None
    if not ok:
        return None
    try:
        user_id, plugin_id, page_id, exp = json.loads(_unb64(payload))
    except (ValueError, TypeError):
        return None
    if (isinstance(user_id, bool) or not isinstance(user_id, int) or not isinstance(plugin_id, str)
            or not isinstance(page_id, str) or isinstance(exp, bool) or not isinstance(exp, int)):
        return None
    if (time.time() if now is None else now) >= exp:
        raise Expired()
    return user_id, plugin_id, page_id


def parse_range(header: Optional[str], size: int) -> Optional[Tuple[int, int]]:
    """``(first, last)`` of a single ``bytes=a-b`` range within ``size`` bytes, ``None`` for no or an unusable
    header (the caller then sends the whole body). Raises ``ValueError`` for a range outside the body (416)."""
    if not header or not header.startswith("bytes=") or "," in header:
        return None
    first, _, last = header[6:].strip().partition("-")
    try:
        if first == "":
            length = int(last)
            if length <= 0:
                raise ValueError
            return max(size - length, 0), size - 1
        start = int(first)
        end = int(last) if last else size - 1
    except ValueError:
        raise ValueError("unsatisfiable") from None
    if start >= size or end < start:
        raise ValueError("unsatisfiable")
    return start, min(end, size - 1)
