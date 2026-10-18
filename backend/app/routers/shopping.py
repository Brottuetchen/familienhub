"""Shopping list endpoints. Source: Home Assistant to-do lists or the hub's own list (``hub_shopping``)."""

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


def _hub():
    """The hub's own list, if the ``hub_shopping`` plugin is active."""
    from app.plugins.registry import plugin_registry
    from app.services.hub_shopping import HubShopping

    plugin = plugin_registry.get("hub_shopping")
    return HubShopping() if plugin and plugin.active else None


def _hub_source():
    """Hub list instead of Home Assistant: chosen explicitly (SHOPPING_SOURCE) or because HA is not set up."""
    from app.plugins.base import get_setting

    choice = str(get_setting("SHOPPING_SOURCE") or "").strip()
    if choice == "mealie":
        from app.plugins.registry import plugin_registry
        from app.services.mealie import MealieShopping

        if plugin_registry.serves("shopping", "mealie"):
            return MealieShopping()
    if choice == "hub_shopping" or (choice != "homeassistant" and _ha() is None):
        return _hub()
    return None  # Home Assistant


@router.get("")
async def list_items(_: User = Depends(get_current_user)):
    """Liefert manuelle + Rezeptzutaten getrennt."""
    hub = _hub_source()
    if hub:
        return await hub.groups()
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
    hub = _hub_source()
    if hub:
        async def add_hub():
            if not await hub.add(data.item, user.id):
                raise HTTPException(422, "Artikel fehlt")
            return {"status": "ok"}

        return await idempotency.run(user.id, "shopping:add", idempotency_key, add_hub)
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
    hub = _hub_source()
    if hub:
        if not await hub.set_done(uid, data.done):
            raise HTTPException(404, "Eintrag nicht gefunden")
        return {"status": "ok"}
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
    hub = _hub_source()
    if hub:
        if not await hub.delete(uid):
            raise HTTPException(404, "Eintrag nicht gefunden")
        return {"status": "ok"}
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
    hub = _hub_source()
    if hub:
        return await hub.recent()
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


async def add_to_shopping(items, user_id: Optional[int]) -> int:
    """Adds items to the family's current shopping list (hub, Mealie or Home Assistant). Returns how many went in."""
    items = [i.strip() for i in items if i and i.strip()]
    source = _hub_source()
    added = 0
    if source:
        for item in items:
            try:
                if await source.add(item, user_id):
                    added += 1
            except Exception as exc:  # noqa: BLE001 - one failed item must not stop the others
                logger.warning("Artikel nicht hinzugefügt: %s", type(exc).__name__)
        return added
    ha = _ha()
    if ha:
        for item in items:
            if await ha.add_todo_item(settings.ha_shopping_todo, item):
                added += 1
    return added
