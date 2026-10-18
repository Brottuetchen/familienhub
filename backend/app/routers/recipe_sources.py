"""Recipe sources (Cookidoo, Mealie …) behind one API: search, plan on a day, ingredients onto the shopping list.

The app lists ``GET /api/recipe-sources`` and offers "Recipe from <name>" for each. ``/api/cookidoo/…`` stays for
older app versions.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

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
async def to_shopping(source_id: str, data: ShoppingIn, _: User = Depends(require_min_role(ROLE_PARTNER))):
    service = _source(source_id)
    try:
        return {"added": await service.ingredients_to_shopping(data.recipe_ids)}
    except _errors() as exc:
        raise HTTPException(503, str(exc)) from exc
