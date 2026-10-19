"""Data sources provided by external plugins: shopping list, recipes.

A plugin offers data by overriding hooks of ``Plugin`` (see ``docs/plugins.md``, "Data sources"). This module is the
hub side: the plugin-facing interface of a shopping list (``ShoppingConnector``) and thin adapters that give plugin
data the same shape as the built-in sources. Every call to a plugin has a timeout and every exception is caught:
the adapters return empty data plus a status, or raise ``PluginSourceError`` (an HTTP 502 for write calls), never a
raw plugin exception.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, Awaitable, Dict, List, Optional

from fastapi import HTTPException

from app.core.logging_config import get_logger

logger = get_logger("plugins.sources")

# Seconds a plugin gets for one call
PLUGIN_TIMEOUT = 15.0


class PluginSourceError(Exception):
    """A plugin could not deliver (down, timed out, raised, answered nonsense). The message is safe to show."""


async def safe_call(plugin_id: str, what: str, coro: Awaitable[Any], timeout: Optional[float] = None) -> Any:
    """Await a plugin call with a timeout; every failure becomes a ``PluginSourceError`` (details only in the log)."""
    try:
        return await asyncio.wait_for(coro, timeout or PLUGIN_TIMEOUT)
    except asyncio.TimeoutError as exc:
        logger.warning("Plugin %s: %s timed out", plugin_id, what)
        raise PluginSourceError("Plugin antwortet nicht rechtzeitig") from exc
    except PluginSourceError:
        raise
    except Exception as exc:  # noqa: BLE001 - a plugin must never break the hub
        logger.warning("Plugin %s: %s failed: %s", plugin_id, what, type(exc).__name__)
        raise PluginSourceError("Plugin nicht erreichbar") from exc


def overrides(plugin: Any, hook: str) -> bool:
    """Does this plugin implement the hook (instead of inheriting the do-nothing default of ``Plugin``)?"""
    from app.plugins.base import Plugin

    return getattr(type(plugin), hook, None) is not getattr(Plugin, hook)


# --- shopping list ---------------------------------------------------------------------------------------------


class ShoppingConnector:
    """Interface of a plugin's shopping list. Subclass it and return an instance from ``Plugin.shopping_connector``.

    Items are dicts ``{uid, summary, status, description?, amount?}``; ``status`` is ``needs_action`` (open) or
    ``completed`` (checked). Only ``list_items``, ``add``, ``set_done`` and ``delete`` are required.
    """

    async def list_items(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def add(self, summary: str, user_id: Optional[int] = None, description: Optional[str] = None) -> bool:
        raise NotImplementedError

    async def set_done(self, uid: str, done: bool) -> bool:
        raise NotImplementedError

    async def delete(self, uid: str) -> bool:
        raise NotImplementedError

    async def rename(self, uid: str, summary: str) -> bool:
        """Optional. Without it, equal recipe ingredients are listed one by one instead of merged into one entry."""
        return False


def _clean_item(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict) or raw.get("uid") in (None, ""):
        return None
    summary = str(raw.get("summary") or "").strip()
    if not summary:
        return None
    done = str(raw.get("status") or "").lower() in ("completed", "done", "checked") or raw.get("done") is True
    item: Dict[str, Any] = {"uid": str(raw["uid"]), "summary": summary[:200],
                            "status": "completed" if done else "needs_action"}
    for key in ("description", "amount"):
        if raw.get(key) not in (None, ""):
            item[key] = str(raw[key])[:200]
    if "description" not in item and "amount" in item:
        item["description"] = item["amount"]  # the app shows the description under the item
    return item


class PluginShopping:
    """Gives a plugin's ``ShoppingConnector`` the interface of the hub list (``app.services.hub_shopping``)."""

    def __init__(self, plugin_id: str, connector: ShoppingConnector):
        self.plugin_id = plugin_id
        self.scope = f"plugin:{plugin_id}"  # key of recipe references (``shopping_recipes``)
        self.connector = connector

    async def _items(self) -> List[Dict[str, Any]]:
        rows = await safe_call(self.plugin_id, "shopping list", self.connector.list_items())
        if not isinstance(rows, (list, tuple)):
            raise PluginSourceError("Plugin lieferte keine Liste")
        return [i for i in map(_clean_item, rows) if i]

    async def groups(self) -> Dict[str, Any]:
        from app.services import shopping_recipes

        try:
            items = await self._items()
        except PluginSourceError as exc:
            return {"status": "unavailable", "error": str(exc), "groups": []}
        items.sort(key=lambda i: i["status"] == "completed")  # open first, stable
        return {"status": "ok", "error": None,
                "groups": [{"key": "manual", "entity": self.plugin_id,
                            "items": shopping_recipes.attach(self.scope, items)}]}

    async def open_items(self) -> List[Dict[str, Any]]:
        return [{"uid": i["uid"], "summary": i["summary"]} for i in await self._items() if i["status"] == "needs_action"]

    async def _write(self, what: str, coro: Awaitable[Any]) -> bool:
        try:
            return bool(await safe_call(self.plugin_id, what, coro))
        except PluginSourceError as exc:
            raise HTTPException(502, str(exc)) from exc

    async def add(self, summary: str, user_id: Optional[int]) -> bool:
        summary = summary.strip()[:200]
        if not summary:
            return False
        return await self._write("add item", self.connector.add(summary, user_id))

    async def rename(self, uid: str, summary: str) -> bool:
        try:
            return bool(await safe_call(self.plugin_id, "rename item", self.connector.rename(uid, summary.strip()[:200])))
        except PluginSourceError:
            return False  # the caller lists the line on its own then

    async def set_done(self, uid: str, done: bool) -> bool:
        return await self._write("check item", self.connector.set_done(uid, done))

    async def delete(self, uid: str) -> bool:
        return await self._write("delete item", self.connector.delete(uid))

    async def recent(self) -> List[str]:
        try:
            done = [i for i in await self._items() if i["status"] == "completed"]
        except PluginSourceError:
            return []
        seen, out = set(), []
        for item in reversed(done):  # newest last in most systems
            if item["summary"].lower() not in seen:
                seen.add(item["summary"].lower())
                out.append(item["summary"])
        return out[:30]

    async def open_count(self) -> int:
        try:
            return sum(1 for i in await self._items() if i["status"] == "needs_action")
        except PluginSourceError:
            return 0


def shopping_source(plugin: Any) -> Optional[PluginShopping]:
    """The shopping adapter of a plugin, or None when it has no (working) connector."""
    from app.core.database import SessionLocal

    try:
        with SessionLocal() as db:
            connector = plugin.shopping_connector(db)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Plugin %s: shopping_connector failed: %s", plugin.id, type(exc).__name__)
        return None
    return PluginShopping(plugin.id, connector) if connector is not None else None


# --- recipes ---------------------------------------------------------------------------------------------------


def _text(value: Any, limit: int = 300) -> Optional[str]:
    return str(value).strip()[:limit] if value not in (None, "") else None


def _minutes(value: Any) -> Optional[int]:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else None


def _lines(value: Any) -> List[str]:
    return [str(x).strip() for x in value if str(x).strip()] if isinstance(value, (list, tuple)) else []


class PluginRecipes:
    """Recipe service of a plugin with the interface of the Mealie/Cookidoo services (``recipe_sources`` router).

    Planning a recipe on a day is stored by the hub (``meal_plan`` rows with ``source`` = plugin id).
    """

    def __init__(self, plugin: Any):
        self.plugin = plugin
        self.id = plugin.id
        # a plugin that can put ingredients on its own list is asked first (see ``recipes_to_shopping``)
        self.prefers_native_shopping = overrides(plugin, "recipe_to_shopping")

    async def search(self, query: str, limit: int = 30) -> Dict[str, Any]:
        rows = await safe_call(self.id, "recipe search", self.plugin.recipe_search(query, limit))
        if not isinstance(rows, (list, tuple)):
            raise PluginSourceError("Plugin lieferte keine Liste")
        items = []
        for r in rows[:limit]:
            if not isinstance(r, dict) or r.get("id") in (None, "") or not _text(r.get("name")):
                continue
            thumb = _text(r.get("thumbnail") or r.get("image"), 1000)
            items.append({"id": str(r["id"]), "name": _text(r["name"]), "image": thumb, "thumbnail": thumb,
                          "url": _text(r.get("url"), 1000), "minutes": _minutes(r.get("minutes"))})
        return {"items": items, "total": len(items)}

    async def recipe(self, recipe_id: str) -> Dict[str, Any]:
        r = await safe_call(self.id, "recipe", self.plugin.recipe(recipe_id))
        if not isinstance(r, dict) or not r.get("name"):
            raise PluginSourceError("Rezept nicht gefunden")
        servings = r.get("servings")
        return {"id": str(r.get("id") or recipe_id), "name": _text(r["name"]), "image": _text(r.get("image"), 1000),
                "url": _text(r.get("url"), 1000), "minutes": _minutes(r.get("minutes")),
                "servings": servings if isinstance(servings, (int, float)) and servings > 0 else None,
                "ingredients": _lines(r.get("ingredients")), "steps": _lines(r.get("steps"))}

    async def add(self, day: date, recipe_id: str) -> None:
        from app.core.database import SessionLocal
        from app.models.recipe import MealPlanEntry

        detail = await self.recipe(recipe_id)
        meta = {k: detail.get(k) for k in ("image", "url", "minutes")}
        with SessionLocal() as db:
            exists = db.query(MealPlanEntry).filter_by(date=day.isoformat(), source=self.id,
                                                       external_id=str(recipe_id)).first()
            if exists is None:
                db.add(MealPlanEntry(date=day.isoformat(), meal_type="dinner", custom_title=detail["name"],
                                     source=self.id, external_id=str(recipe_id), meta=meta))
                db.commit()

    async def remove(self, day: date, recipe_id: str) -> None:
        from app.core.database import SessionLocal
        from app.models.recipe import MealPlanEntry

        with SessionLocal() as db:
            db.query(MealPlanEntry).filter_by(date=day.isoformat(), source=self.id,
                                              external_id=str(recipe_id)).delete()
            db.commit()

    async def ingredients_to_shopping(self, recipe_ids: List[str], user_id: Optional[int] = None) -> int:
        """The plugin's own list if it has one, otherwise the ingredients go onto the hub's shopping list."""
        if self.prefers_native_shopping:
            done = await safe_call(self.id, "recipe to shopping", self.plugin.recipe_to_shopping(list(recipe_ids), user_id))
            if isinstance(done, int) and not isinstance(done, bool):
                return done
        from app.routers.shopping import add_recipe_ingredients

        entries = []
        for rid in recipe_ids:
            detail = await self.recipe(rid)
            if detail["ingredients"]:
                entries.append((detail["name"] or "", detail["ingredients"]))
        return await add_recipe_ingredients(entries, user_id) if entries else 0


def recipe_plugins() -> List[Any]:
    """Active external plugins with capability ``meal_planning`` that implement ``recipe_search``."""
    from app.plugins.registry import plugin_registry

    return [p for p in plugin_registry.providers("meal_planning") if not p.builtin and overrides(p, "recipe_search")]


def recipe_service(source_id: str) -> Optional[PluginRecipes]:
    for plugin in recipe_plugins():
        if plugin.id == source_id:
            return PluginRecipes(plugin)
    return None


def planned_entries(db, start: date, end: date) -> Dict[str, List[Dict[str, Any]]]:
    """Plugin recipes planned in the hub in a range, as meal-plan entries by ISO day."""
    from app.models.recipe import MealPlanEntry
    from app.plugins.registry import plugin_registry

    rows = (db.query(MealPlanEntry).filter(MealPlanEntry.source.isnot(None), MealPlanEntry.date >= start.isoformat(),
                                           MealPlanEntry.date <= end.isoformat()).order_by(MealPlanEntry.id).all())
    out: Dict[str, List[Dict[str, Any]]] = {}
    for e in rows:
        plugin = plugin_registry.get(e.source)
        if plugin is None or not plugin.active:
            continue  # plugin removed or switched off: the entry stays stored but is hidden
        meta = e.meta if isinstance(e.meta, dict) else {}
        out.setdefault(e.date, []).append({
            "title": e.custom_title or "Mahlzeit", "source": e.source, "source_name": plugin.name,
            "recipe_id": e.external_id, "entry_id": e.id, "meal_type": e.meal_type,
            "minutes": meta.get("minutes"), "image": meta.get("image"), "url": meta.get("url")})
    return out

