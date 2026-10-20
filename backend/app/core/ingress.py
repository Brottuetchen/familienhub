"""Serving under a sub-path (Home Assistant ingress, reverse proxy with a prefix).

The proxy strips the prefix before the request reaches the hub, so routing is unchanged. The prefix only matters
where the hub writes absolute URLs: the `<base href>` of the web app, the manifest, cookie paths and redirects.

Where the prefix comes from, in this order:
1. `X-Ingress-Path` header, only if TRUST_INGRESS_HEADER is on AND the direct peer is in INGRESS_PROXY_IPS
   (Home Assistant's ingress gateway, 172.30.32.2) AND the value has the shape `/api/hassio_ingress/<token>`.
2. ROOT_PATH setting (a fixed prefix chosen by the operator).
3. No prefix: the hub lives at `/` exactly as before.

The header value ends up inside HTML, therefore anything that does not match the strict patterns is dropped.
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from typing import Optional

from starlette.requests import Request

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger("familienhub.ingress")

INGRESS_HEADER = "x-ingress-path"
# What Home Assistant sends: /api/hassio_ingress/<token> (token is urlsafe base64-ish)
_HEADER_RE = re.compile(r"^/api/hassio_ingress/[A-Za-z0-9_-]{1,128}$")
# Operator-chosen ROOT_PATH: one or more plain segments, no trailing slash, no dot segments
_ROOT_RE = re.compile(r"^(?:/[A-Za-z0-9_~-][A-Za-z0-9._~-]{0,63}){1,8}$")

_warned_root = False
# Prefix of the request being handled; read by the cookie helpers (they have no request at hand)
current_prefix: ContextVar[str] = ContextVar("fh_path_prefix", default="")


def valid_header_prefix(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip().rstrip("/")
    return value if _HEADER_RE.match(value) else None


def valid_root_path(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip().rstrip("/")
    if not value:
        return None
    if _ROOT_RE.match(value) and ".." not in value.split("/"):
        return value
    return None


def configured_root_path() -> str:
    global _warned_root
    raw = (settings.root_path or "").strip().rstrip("/")
    ok = valid_root_path(raw)
    if raw and not ok and not _warned_root:
        _warned_root = True
        logger.warning("ROOT_PATH %r is not a plain path like /hub - ignored", raw)
    return ok or ""


def _trusted_peers() -> set[str]:
    return {p.strip() for p in settings.ingress_proxy_ips.split(",") if p.strip()}


def ingress_header_prefix(request: Request) -> str:
    """Validated prefix from X-Ingress-Path, or "" when the header is absent, untrusted or malformed."""
    raw = request.headers.get(INGRESS_HEADER)
    if raw is None or not settings.trust_ingress_header:
        return ""
    peer = request.client.host if request.client else ""
    if peer not in _trusted_peers():
        return ""
    return valid_header_prefix(raw) or ""


def resolve_prefix(request: Request) -> str:
    """Path prefix the browser sees in front of the hub ("" or e.g. "/api/hassio_ingress/abc"), no trailing slash."""
    return ingress_header_prefix(request) or configured_root_path()


def cookie_path() -> str:
    """Path attribute for auth cookies: the prefix of the current request, so they never leak to other apps."""
    return current_prefix.get() or "/"
