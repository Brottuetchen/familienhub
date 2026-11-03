"""Pages that plugins serve themselves (``Plugin.page``), opened in the browser without the app's bearer token.

- ``GET /api/plugin-pages``: the pages of all active plugins (for *More* in the app).
- ``POST /api/plugin-pages/{plugin}/{page}/link``: a short-lived signed link for the logged-in person.
- ``GET /plugin-pages/{token}/{path}``: the page and its relative assets, authorised by the token alone.

See ``docs/plugins.md``, "Plugin pages". The served route is outside ``/api`` and registered before the frontend
mount, so the web app's static files do not swallow it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import i18n
from app.core.database import get_db
from app.core.logging_config import get_logger
from app.core.security import get_current_user
from app.models.user import User
from app.plugins.hooks import MAX_PAGE_PATH, clean_page_path, run_page
from app.plugins.manifest import ID_RE, PAGE_ID_RE, localized
from app.plugins.registry import plugin_registry
from app.services import plugin_pages

logger = get_logger("router.plugin_pages")
router = APIRouter(tags=["plugin-pages"])

NOT_FOUND = "Seite nicht gefunden"
# What a plugin page may load: its own files, inline scripts and styles (a single-file page is the common case),
# images and media from the hub, small inline images. Nothing from other servers.
PAGE_HEADERS = {
    "Content-Security-Policy": ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                                "img-src 'self' data:; media-src 'self'; object-src 'none'; base-uri 'self'; "
                                "form-action 'self'; frame-ancestors 'none'"),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "private, no-store",
    "X-Frame-Options": "DENY",
}


def _page_of(plugin_id: str, page_id: str):
    plugin = plugin_registry.get(plugin_id) if ID_RE.match(plugin_id) else None
    if plugin is None or not plugin.active or not PAGE_ID_RE.match(page_id):
        return None, None
    page = next((p for p in plugin.pages if p.id == page_id), None)
    return (plugin, page) if page is not None else (None, None)


def _title(page, lang: str) -> str:
    return localized(page.title, lang) if isinstance(page.title, dict) else str(i18n.translate(page.title, lang))


@router.get("/api/plugin-pages")
async def list_pages(request: Request, _: User = Depends(get_current_user)):
    lang = i18n.request_language(request)
    items: List[Dict[str, Any]] = []
    for plugin in plugin_registry.all():
        if not plugin.active:
            continue
        for page in plugin.pages:
            items.append({"plugin": plugin.id, "plugin_name": plugin.name, "id": page.id,
                          "title": _title(page, lang), "icon": page.icon})
    return {"items": items}


class LinkRequest(BaseModel):
    path: str = Field(default="", max_length=MAX_PAGE_PATH + 1)


@router.post("/api/plugin-pages/{plugin_id}/{page_id}/link")
async def page_link(plugin_id: str, page_id: str, data: Optional[LinkRequest] = None,
                    user: User = Depends(get_current_user)):
    plugin, _page = _page_of(plugin_id, page_id)
    if plugin is None:
        raise HTTPException(404, NOT_FOUND)
    path = clean_page_path((data.path if data else "").lstrip("/"))
    if path is None:
        raise HTTPException(422, "Ungültiger Pfad")
    token = plugin_pages.create_token(user.id, plugin.id, page_id)
    return {"url": f"/plugin-pages/{token}/{quote(path)}", "expires_in": plugin_pages.TOKEN_TTL}


def _gone(status: int, text: str) -> HTTPException:
    return HTTPException(status, text, headers={"Cache-Control": "private, no-store"})


@router.get("/plugin-pages/{token}", include_in_schema=False)
async def page_root_redirect(token: str):
    """Relative assets only resolve below a trailing slash."""
    return RedirectResponse(f"{quote(token)}/", status_code=307, headers={"Cache-Control": "private, no-store"})


@router.api_route("/plugin-pages/{token}/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
async def serve_page(token: str, path: str, request: Request, db: Session = Depends(get_db)):
    try:
        claims = plugin_pages.verify_token(token)
    except plugin_pages.Expired:
        raise _gone(410, "Der Link ist abgelaufen. Bitte die Seite in der App neu öffnen") from None
    if claims is None:
        raise _gone(404, NOT_FOUND)
    user_id, plugin_id, page_id = claims
    plugin, _page = _page_of(plugin_id, page_id)
    user = db.get(User, user_id)
    if plugin is None or user is None or not user.is_active:
        raise _gone(404, NOT_FOUND)
    # Encoded separators and dots are refused outright; Starlette hands over the decoded path
    raw = request.scope.get("raw_path") or request.scope["path"].encode()
    lowered = raw.lower()
    if any(bad in lowered for bad in (b"%2f", b"%5c", b"%2e", b"%00", b"%25")) or "%" in path:
        raise _gone(400, "Ungültiger Pfad")
    clean = clean_page_path(path)
    if clean is None:
        raise _gone(400, "Ungültiger Pfad")
    result = await run_page(plugin, user, page_id, clean)
    if result is None:
        raise _gone(404, NOT_FOUND)
    content_type, body = result
    headers = dict(PAGE_HEADERS, **{"Accept-Ranges": "bytes"})
    try:
        span = plugin_pages.parse_range(request.headers.get("range"), len(body))
    except ValueError:
        return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{len(body)}"})
    status = 200
    if span is not None:
        first, last = span
        headers["Content-Range"] = f"bytes {first}-{last}/{len(body)}"
        body, status = body[first:last + 1], 206
    return Response(content=b"" if request.method == "HEAD" else body, status_code=status, media_type=content_type,
                    headers={**headers, "Content-Length": str(len(body))})
