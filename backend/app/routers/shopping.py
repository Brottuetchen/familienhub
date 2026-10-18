"""Einkaufslisten-Endpunkte (HA Todo)."""

import logging

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.connectors.registry import registry
from app.core.security import get_current_user, require_min_role
from app.models.user import User, ROLE_CHILD
from app.services import idempotency

router = APIRouter(prefix="/api/shopping", tags=["shopping"])
logger = logging.getLogger("hermes.shopping")


class AddItemRequest(BaseModel):
    item: str


class UpdateItemRequest(BaseModel):
    done: bool


def _ha():
    c = registry.get("homeassistant")
    if not c or not c.is_configured:
        return None
    return c


@router.get("")
async def list_items(_: User = Depends(get_current_user)):
    """Liefert manuelle + Rezeptzutaten getrennt."""
    ha = _ha()
    if not ha:
        return {
            "status": "not_configured",
            "error": "Home Assistant nicht konfiguriert",
            "groups": [],
        }

    try:
        manual = await ha.get_todo_items(settings.ha_shopping_todo)
        recipe = await ha.get_todo_items(settings.ha_recipe_shopping_todo)

        return {
            "status": "ok",
            "error": None,
            "groups": [
                {
                    "key": "manual",
                    "entity": settings.ha_shopping_todo,
                    "items": manual,
                },
                {
                    "key": "recipes",
                    "entity": settings.ha_recipe_shopping_todo,
                    "items": recipe,
                },
            ],
        }
    except Exception as exc:
        logger.warning("Failed to fetch shopping items: %s", exc, exc_info=True)
        return {
            "status": "unavailable",
            "error": str(exc),
            "groups": [],
        }


@router.post("")
async def add_item(data: AddItemRequest, user: User = Depends(get_current_user),
                   idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")):
    """Fügt ein manuelles Item hinzu. Mit Idempotency-Key (Offline-Warteschlange) höchstens einmal."""
    ha = _ha()
    if not ha:
        raise HTTPException(503, "Home Assistant nicht konfiguriert")

    async def add():
        if not await ha.add_todo_item(settings.ha_shopping_todo, data.item):
            raise HTTPException(502, "Could not add item")
        return {"status": "ok"}

    return await idempotency.run(user.id, "shopping:add", idempotency_key, add)


@router.patch("/{uid}")
async def update_item(uid: str, data: UpdateItemRequest, _: User = Depends(get_current_user)):
    """Markiert done (completed) oder wieder offen (needs_action)."""
    ha = _ha()
    if not ha:
        raise HTTPException(503, "Home Assistant nicht konfiguriert")

    status = "completed" if data.done else "needs_action"
    # Versuche erst manual, dann recipes
    if not await ha.update_todo_item(settings.ha_shopping_todo, uid, status):
        if not await ha.update_todo_item(settings.ha_recipe_shopping_todo, uid, status):
            raise HTTPException(502, "Could not update item")
    return {"status": "ok"}


@router.delete("/{uid}")
async def delete_item(uid: str, _: User = Depends(require_min_role(ROLE_CHILD))):
    """Entfernt Item aus manueller Liste (Rezeptzutaten nicht löschbar)."""
    ha = _ha()
    if not ha:
        raise HTTPException(503, "Home Assistant nicht konfiguriert")

    # Prüfe ob der Eintrag in der Rezeptliste ist (dann 403)
    try:
        recipe_items = await ha.get_todo_items(settings.ha_recipe_shopping_todo)
        recipe_uids = {item.get("uid") for item in recipe_items}
        if uid in recipe_uids:
            raise HTTPException(403, "Rezeptzutaten können nicht gelöscht werden")
    except HTTPException:
        raise
    except Exception:
        # Wenn wir die Rezeptliste nicht abrufen können, versuchen wir trotzdem zu löschen
        pass

    if not await ha.remove_todo_item(settings.ha_shopping_todo, [uid]):
        raise HTTPException(502, "Could not remove item")
    return {"status": "ok"}


@router.get("/recent")
async def recent_completions(_: User = Depends(get_current_user)):
    """Vorschläge: zuletzt abgehakte freie Artikel (ohne Doppelte), höchstens 30."""
    ha = _ha()
    if not ha:
        return []
    try:
        done = await ha.get_todo_items(settings.ha_shopping_todo, status=["completed"])
    except Exception as exc:
        logger.warning("Failed to fetch completed shopping items: %s", exc)
        return []
    seen, out = set(), []
    for item in reversed(done):  # HA hängt neue hinten an → neueste zuerst
        name = (item.get("summary") or "").strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
        if len(out) >= 30:
            break
    return out
