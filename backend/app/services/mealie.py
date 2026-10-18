"""Mealie (https://mealie.io): recipes, household meal plan and shopping list. API v2 (``/api/households/…``).

One household token for the family (meal plan and shopping list are household data in Mealie, not personal).
Errors come as ``MealieUnavailable`` with a short message, never as raw exceptions into the app.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

import httpx

from app.core.logging_config import get_logger
from app.plugins.base import get_setting

logger = get_logger("service.mealie")


class MealieUnavailable(Exception):
    pass


def plugin_active() -> bool:
    from app.plugins.registry import plugin_registry

    plugin = plugin_registry.get("mealie")
    return bool(plugin and plugin.active)


def _base() -> str:
    return str(get_setting("MEALIE_URL") or "").rstrip("/")


def _public() -> str:
    return str(get_setting("MEALIE_PUBLIC_URL") or "").rstrip("/") or _base()


def _minutes(recipe: Dict[str, Any]) -> Optional[int]:
    seconds = recipe.get("totalTimeSeconds")
    if isinstance(seconds, (int, float)) and seconds > 0:
        return round(seconds / 60)
    return None


class MealieService:
    def __init__(self):
        self._group_slug: Optional[str] = None

    async def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        base, token = _base(), get_setting("MEALIE_TOKEN")
        if not base or not token:
            raise MealieUnavailable("Mealie ist nicht eingerichtet")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.request(method, f"{base}{path}", headers={"Authorization": f"Bearer {token}"}, **kwargs)
        except httpx.HTTPError as exc:
            logger.warning("Mealie nicht erreichbar: %s", type(exc).__name__)
            raise MealieUnavailable("Mealie nicht erreichbar") from exc
        if resp.status_code in (401, 403):
            raise MealieUnavailable("Mealie lehnt den Zugang ab (Token prüfen)")
        if resp.status_code >= 400:
            logger.warning("Mealie %s %s → HTTP %d", method, path, resp.status_code)
            raise MealieUnavailable(f"Mealie antwortet mit HTTP {resp.status_code}")
        return resp.json() if resp.content else None

    async def _recipe_url(self, slug: Optional[str]) -> Optional[str]:
        if not slug:
            return None
        if self._group_slug is None:
            try:
                self._group_slug = (await self._call("GET", "/api/groups/self")).get("slug") or ""
            except MealieUnavailable:
                self._group_slug = ""
        return f"{_public()}/g/{self._group_slug}/r/{slug}" if self._group_slug else f"{_public()}/recipe/{slug}"

    def _image(self, recipe: Dict[str, Any]) -> Optional[str]:
        rid = recipe.get("id")
        return f"{_public()}/api/media/recipes/{rid}/images/min-original.webp" if rid and recipe.get("image") else None

    # --- recipes and meal plan ---

    async def search(self, query: str) -> Dict[str, Any]:
        data = await self._call("GET", "/api/recipes", params={"search": query, "perPage": 30, "page": 1})
        items = [{"id": r["id"], "name": r.get("name") or "", "image": self._image(r), "thumbnail": self._image(r),
                  "url": await self._recipe_url(r.get("slug"))} for r in (data or {}).get("items", [])]
        return {"items": items, "total": (data or {}).get("total", len(items))}

    async def plan_between(self, start: date, end: date) -> Dict[str, List[Dict[str, Any]]]:
        data = await self._call("GET", "/api/households/mealplans", params={
            "start_date": start.isoformat(), "end_date": end.isoformat(), "perPage": 200, "page": 1})
        out: Dict[str, List[Dict[str, Any]]] = {}
        for e in (data or {}).get("items", []):
            recipe = e.get("recipe") or {}
            out.setdefault(e["date"], []).append({
                "title": recipe.get("name") or e.get("title") or "Mahlzeit",
                "description": e.get("text") or None,
                "source": "mealie", "recipe_id": e.get("recipeId"), "entry_id": e.get("id"),
                "meal_type": e.get("entryType"), "minutes": _minutes(recipe), "image": self._image(recipe),
                "url": await self._recipe_url(recipe.get("slug")),
            })
        return out

    async def add(self, day: date, recipe_id: str) -> None:
        await self._call("POST", "/api/households/mealplans",
                         json={"date": day.isoformat(), "entryType": "dinner", "recipeId": recipe_id})

    async def remove(self, day: date, recipe_id: str) -> None:
        plan = await self.plan_between(day, day)
        for entry in plan.get(day.isoformat(), []):
            if entry["recipe_id"] == recipe_id and entry["entry_id"] is not None:
                await self._call("DELETE", f"/api/households/mealplans/{entry['entry_id']}")
                return

    # --- shopping list ---

    async def _list_id(self) -> str:
        wanted = str(get_setting("MEALIE_SHOPPING_LIST") or "").strip().lower()
        lists = (await self._call("GET", "/api/households/shopping/lists", params={"perPage": 100, "page": 1}) or {}).get("items", [])
        if not lists:
            raise MealieUnavailable("In Mealie gibt es noch keine Einkaufsliste")
        chosen = next((entry for entry in lists if wanted and (entry.get("name") or "").strip().lower() == wanted), lists[0])
        return chosen["id"]

    async def ingredients_to_shopping(self, recipe_ids: List[str]) -> int:
        list_id = await self._list_id()
        for rid in recipe_ids:
            await self._call("POST", f"/api/households/shopping/lists/{list_id}/recipe/{rid}")
        return len(recipe_ids)


mealie_service = MealieService()


def _label(item: Dict[str, Any]) -> str:
    return (item.get("display") or item.get("note") or "").strip()


class MealieShopping:
    """Mealie shopping list with the same interface as the hub list (``app.services.hub_shopping``)."""

    async def _items(self) -> List[Dict[str, Any]]:
        list_id = await mealie_service._list_id()
        return (await mealie_service._call("GET", f"/api/households/shopping/lists/{list_id}") or {}).get("listItems", [])

    async def groups(self) -> Dict[str, Any]:
        try:
            items = await self._items()
        except MealieUnavailable as exc:
            return {"status": "unavailable", "error": str(exc), "groups": []}
        return {"status": "ok", "error": None, "groups": [{"key": "manual", "entity": "mealie", "items": [
            {"uid": i["id"], "summary": _label(i), "status": "completed" if i.get("checked") else "needs_action"}
            for i in items]}]}

    async def add(self, summary: str, user_id: Optional[int]) -> bool:
        summary = summary.strip()[:200]
        if not summary:
            return False
        list_id = await mealie_service._list_id()
        await mealie_service._call("POST", "/api/households/shopping/items",
                                   json={"shoppingListId": list_id, "note": summary, "display": summary, "checked": False})
        return True

    async def _get(self, uid: str) -> Optional[Dict[str, Any]]:
        try:
            return await mealie_service._call("GET", f"/api/households/shopping/items/{uid}")
        except MealieUnavailable:
            return None

    async def set_done(self, uid: str, done: bool) -> bool:
        item = await self._get(uid)
        if not item:
            return False
        # PUT needs the complete item; only "checked" changes
        await mealie_service._call("PUT", f"/api/households/shopping/items/{uid}", json={**item, "checked": done})
        return True

    async def delete(self, uid: str) -> bool:
        if not await self._get(uid):
            return False
        await mealie_service._call("DELETE", f"/api/households/shopping/items/{uid}")
        return True

    async def recent(self) -> List[str]:
        try:
            items = await self._items()
        except MealieUnavailable:
            return []
        seen, out = set(), []
        for i in reversed([i for i in items if i.get("checked")]):
            name = _label(i)
            if name and name.lower() not in seen:
                seen.add(name.lower())
                out.append(name)
        return out[:30]

    async def open_count(self) -> int:
        try:
            return sum(1 for i in await self._items() if not i.get("checked"))
        except MealieUnavailable:
            return 0
