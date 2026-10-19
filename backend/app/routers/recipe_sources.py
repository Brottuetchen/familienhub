"""Recipe sources (Cookidoo, Mealie …) behind one API: search, plan on a day, ingredients onto the shopping list.

The app lists ``GET /api/recipe-sources`` and offers "Recipe from <name>" for each. ``/api/cookidoo/…`` stays for
older app versions.
"""

from __future__ import annotations

import json
import time
from datetime import date
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_min_role
from app.models.user import ROLE_PARTNER, User

router = APIRouter(prefix="/api/recipe-sources", tags=["meals"])


def _services() -> Dict[str, Any]:
    from app.services.cookidoo import cookidoo_service
    from app.services.mealie import mealie_service

    return {"cookidoo": cookidoo_service, "mealie": mealie_service}


def _errors() -> tuple:
    from app.services.cookidoo import CookidooUnavailable
    from app.services.mealie import MealieUnavailable

    return (CookidooUnavailable, MealieUnavailable)


def _source(source_id: str):
    from app.plugins.registry import plugin_registry

    service = _services().get(source_id)
    if service is None or not plugin_registry.serves("meal_planning", source_id):
        raise HTTPException(409, "Diese Rezeptquelle ist nicht aktiv")
    return service


@router.get("")
async def list_sources(_: User = Depends(get_current_user)):
    from app.plugins.registry import plugin_registry

    return [{"id": p.id, "name": p.name} for p in plugin_registry.providers("meal_planning") if p.id in _services()]


@router.get("/{source_id}/search")
async def search(source_id: str, q: str, _: User = Depends(get_current_user)):
    service = _source(source_id)
    if len(q.strip()) < 3:
        return {"status": "ok", "error": None, "items": [], "total": 0}
    try:
        return {"status": "ok", "error": None, **await service.search(q.strip())}
    except _errors() as exc:
        return {"status": "unavailable", "error": str(exc), "items": [], "total": 0}


# Quick view details of external recipes: same recipe, same answer for everybody, so a short shared cache
# spares the sources (and Cookidoo's login) when the family browses. No personal data is stored.
_DETAIL_TTL = 3600
_DETAIL_MAX = 300
_details: Dict[Tuple[str, str], Tuple[float, Dict[str, Any]]] = {}


def _detail(title: Any, image: Any, minutes: Any, servings: Any, ingredients: Any, steps: Any, url: Any, source: str,
            recipe_id: str) -> Dict[str, Any]:
    return {"status": "ok", "error": None, "id": recipe_id, "source": source, "title": title or "", "image": image,
            "minutes": minutes, "servings": servings, "ingredients": [str(i) for i in ingredients or []],
            "steps": [str(x) for x in steps or []], "url": url}


def _failed(source: str, recipe_id: str, error: str) -> Dict[str, Any]:
    return {**_detail("", None, None, None, [], [], None, source, recipe_id), "status": "unavailable", "error": error}


def _hub_recipe(recipe_id: str, db: Session) -> Dict[str, Any]:
    from app.models.recipe import Recipe

    r = db.query(Recipe).filter(Recipe.id == int(recipe_id)).first() if recipe_id.isdigit() else None
    if r is None:
        return _failed("hub", recipe_id, "Rezept nicht gefunden")
    try:
        ingredients = json.loads(r.ingredients_json or "[]")
    except (ValueError, TypeError):
        ingredients = []
    steps = [line.strip() for line in (r.instructions or "").splitlines() if line.strip()]
    return _detail(r.title, None, r.prep_minutes, r.servings, ingredients, steps, r.source_url, "hub", recipe_id)


@router.get("/{source_id}/recipes/{recipe_id}")
async def recipe_details(source_id: str, recipe_id: str, _: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    """One shape for the app's recipe quick view: hub recipe book, Cookidoo, Mealie. Fails softly."""
    if source_id == "hub":
        return _hub_recipe(recipe_id, db)
    service = _source(source_id)
    key = (source_id, recipe_id)
    hit = _details.get(key)
    if hit and time.monotonic() - hit[0] < _DETAIL_TTL:
        return hit[1]
    try:
        raw = await (service.recipe(recipe_id))
    except _errors() as exc:
        return _failed(source_id, recipe_id, str(exc))
    result = _detail(raw.get("name"), raw.get("image"), raw.get("minutes"), raw.get("servings"), raw.get("ingredients"),
                     raw.get("steps"), raw.get("url"), source_id, recipe_id)
    if len(_details) >= _DETAIL_MAX:
        _details.pop(min(_details, key=lambda k: _details[k][0]))
    _details[key] = (time.monotonic(), result)
    return result


class PlanIn(BaseModel):
    date: date
    recipe_id: str = Field(min_length=1, max_length=100)


class ShoppingIn(BaseModel):
    recipe_ids: List[str] = Field(min_length=1, max_length=20)


@router.post("/{source_id}/plan")
async def plan(source_id: str, data: PlanIn, _: User = Depends(require_min_role(ROLE_PARTNER))):
    service = _source(source_id)
    try:
        await service.add(data.date, data.recipe_id)
    except _errors() as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"date": data.date.isoformat(), "recipe_id": data.recipe_id}


@router.delete("/{source_id}/plan/{day}/{recipe_id}")
async def unplan(source_id: str, day: date, recipe_id: str, _: User = Depends(require_min_role(ROLE_PARTNER))):
    service = _source(source_id)
    try:
        await service.remove(day, recipe_id)
    except _errors() as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"removed": True}


@router.post("/{source_id}/shopping")
async def to_shopping(source_id: str, data: ShoppingIn, user: User = Depends(require_min_role(ROLE_PARTNER))):
    from app.routers.shopping import recipes_to_shopping

    service = _source(source_id)
    try:
        return {"added": await recipes_to_shopping(service, data.recipe_ids, user.id)}
    except _errors() as exc:
        raise HTTPException(503, str(exc)) from exc
