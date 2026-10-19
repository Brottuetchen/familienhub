"""Example plugin: shows notes from an example service. Copy this file and adapt it.

What it demonstrates:

- one plain setting (the address) and one secret (the token), both read with ``get_setting``,
- one endpoint below ``/api/plugins/<id>/`` that returns ``{status, error, items}`` and never raises,
- texts in the user's language (``request_language``).
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, Request

from app.core.i18n import request_language
from app.core.logging_config import get_logger
from app.core.security import get_current_user
from app.plugins import Plugin, Setting, get_setting

logger = get_logger("plugin.example_notes")

# Installed plugins must serve their routes below /api/plugins/<id>/; the hub adds the login check.
router = APIRouter(prefix="/api/plugins/example_notes", tags=["example_notes"])

UNAVAILABLE = {"de": "Der Notiz-Dienst ist nicht erreichbar", "en": "The notes service is not reachable"}


def _answer(status: str, items=None, error=None) -> dict:
    return {"status": status, "error": error, "items": items or []}


@router.get("/items")
async def items(request: Request, _user=Depends(get_current_user)) -> dict:
    """Notes from the service. A service that is down gives ``unavailable`` plus a message, never an error page."""
    base = str(get_setting("EXAMPLE_NOTES_URL") or "").rstrip("/")
    if not base:
        return _answer("not_configured")
    token = get_setting("EXAMPLE_NOTES_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with httpx.AsyncClient(timeout=6, follow_redirects=False) as client:
            response = await client.get(f"{base}/notes", headers=headers)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ValueError("unexpected answer")
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Notes service not usable: %s", exc.__class__.__name__)  # never log tokens or addresses
        return _answer("unavailable", error=UNAVAILABLE[request_language(request)])
    return _answer("ok", items=[
        {"id": str(note.get("id", "")), "title": str(note.get("title", ""))} for note in data if isinstance(note, dict)
    ])


class ExampleNotesPlugin(Plugin):
    def __init__(self) -> None:
        super().__init__(
            id="example_notes",  # same as "id" in familienhub-plugin.json
            name="Example notes",
            version="0.1.0",
            description="Shows notes from an example service",
            capabilities=frozenset(),  # e.g. frozenset({"shopping"}); must be listed in the manifest too
            settings=(
                # every key must be listed in familienhub-plugin.json and start with the id in capitals
                Setting("EXAMPLE_NOTES_URL", "Address of the notes service"),
                Setting("EXAMPLE_NOTES_TOKEN", "Access token", secret=True, required=False),
            ),
        )

    def routers(self):
        return [router]
