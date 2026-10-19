"""Shopping list endpoints. Source: Home Assistant to-do lists or the hub's own list (``hub_shopping``)."""

import logging

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.connectors.registry import registry
from app.core.security import get_current_user, require_min_role
from app.models.user import User, ROLE_CHILD
from app.services import idempotency, shopping_recipes
from app.services.ingredients import OpenItem, plan_merge

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
        manual = shopping_recipes.attach(f"ha:{settings.ha_shopping_todo}",
                                         await ha.get_todo_items(settings.ha_shopping_todo))
        recipe = await ha.get_todo_items(settings.ha_recipe_shopping_todo)
        for item in recipe:
            item.setdefault("recipes", [])

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


async def add_recipe_ingredients(entries, user_id: Optional[int]) -> int:
    """Puts recipe ingredients on the list and merges equal ones (#70).

    ``entries`` is ``[(recipe name, [ingredient lines])]``. Lines are merged with each other and with the open entries
    of the list ("200 g Zwiebeln" + "1 Zwiebel" -> "1 Zwiebel + 200 g"); the recipe names stay on the entry (#69). A
    recipe that is already on an entry is not added again. Returns how many lines were taken in. A Mealie list is not
    merged here (Mealie merges recipe ingredients itself).
    """
    new = [(line.strip(), name or "") for name, lines in entries for line in lines if line and line.strip()]
    if not new:
        return 0
    source = _hub_source()
    if source is not None:
        from app.services.hub_shopping import HubShopping

        scope = "hub" if isinstance(source, HubShopping) else ""
    else:
        ha = _ha()
        if ha is None:
            return 0
        scope = f"ha:{settings.ha_shopping_todo}"
    existing = []
    if scope:
        try:
            if source is not None:
                rows = await source.open_items()
            else:
                rows = [i for i in await ha.get_todo_items(settings.ha_shopping_todo) if i.get("summary")]
            refs = shopping_recipes.lookup(scope, [r["summary"] for r in rows], prune=False)
            existing = [OpenItem(str(r["uid"]), r["summary"], refs.get(shopping_recipes.key(r["summary"]), []))
                        for r in rows]
        except Exception as exc:  # noqa: BLE001 - without the open entries we only add (no merge into them)
            logger.warning("Open shopping entries not read: %s", type(exc).__name__)
    ops, handled = plan_merge(existing, new)

    async def add(summary: str) -> bool:
        if source is not None:
            return bool(await source.add(summary, user_id))
        return bool(await ha.add_todo_item(settings.ha_shopping_todo, summary))

    async def rename(uid: str, summary: str) -> bool:
        if source is not None:
            return bool(await source.rename(uid, summary))
        return bool(await ha.rename_todo_item(settings.ha_shopping_todo, uid, summary))

    done = 0
    old_text = {o.uid: o.summary for o in existing}
    for op in ops:
        try:
            if op.uid is None:
                if not await add(op.summary):
                    continue
                done += 1 + len(op.absorbed)
                if scope and op.recipes:
                    shopping_recipes.store(scope, op.summary, op.recipes)
                continue
            if op.changed_text and not await rename(op.uid, op.summary):
                # could not merge into the entry: list the absorbed lines on their own
                for raw, recipe in op.absorbed:
                    if await add(raw):
                        done += 1
                        if scope and recipe:
                            shopping_recipes.store(scope, raw, [recipe])
                continue
            done += len(op.absorbed)
            if scope:
                shopping_recipes.store(scope, op.summary, op.recipes, replace_key=old_text.get(op.uid, ""))
        except Exception as exc:  # noqa: BLE001 - one failed entry must not stop the others
            logger.warning("Zutat nicht hinzugefügt: %s", type(exc).__name__)
    return done


async def recipes_to_shopping(service, recipe_ids, user_id: Optional[int] = None) -> int:
    """Ingredients of Cookidoo/Mealie recipes via ``add_recipe_ingredients`` (merged); a recipe whose details cannot be
    read goes through the service's own shopping list instead. Raises the service's error when that fails too."""
    from app.services.mealie import MealieShopping, mealie_service

    entries, native = [], []
    own_list = service is mealie_service and isinstance(_hub_source(), MealieShopping)  # Mealie merges itself
    for rid in recipe_ids:
        if own_list:
            native.append(rid)
            continue
        try:
            detail = await service.recipe(rid)
            if not detail.get("ingredients"):
                raise ValueError("no ingredients")
            entries.append((detail.get("name") or "", detail["ingredients"]))
        except Exception as exc:  # noqa: BLE001 - details are optional, the native list is the fallback
            logger.info("Recipe details not available (%s), using the source's own list", type(exc).__name__)
            native.append(rid)
    count = await add_recipe_ingredients(entries, user_id) if entries else 0
    if native:
        count += await service.ingredients_to_shopping(native)
    return count
