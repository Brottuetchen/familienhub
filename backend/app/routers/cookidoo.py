"""Cookidoo: Rezepte suchen, Wochenplan schreiben, Zutaten auf die Einkaufsliste (#27).

Lesen degradiert sanft ({status, error, …}). Schreiben ohne Einrichtung oder bei Störung → 503.
"""

from __future__ import annotations

from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.models.user import User
from app.services.cookidoo import CookidooUnavailable, cookidoo_service

router = APIRouter(prefix="/api/cookidoo", tags=["cookidoo"])


def _status() -> str:
    return "unavailable" if cookidoo_service.configured else "not_configured"


@router.get("/search")
async def search(q: str, page: int = 0, _: User = Depends(get_current_user)):
    if not cookidoo_service.configured:
        return {"status": "not_configured", "error": "Cookidoo ist nicht eingerichtet", "items": [], "total": 0}
    if len(q.strip()) < 2:
        return {"status": "ok", "error": None, "items": [], "total": 0}
    try:
        found = await cookidoo_service.search(q.strip(), page=max(0, page))
    except CookidooUnavailable as exc:
        return {"status": _status(), "error": str(exc), "items": [], "total": 0}
    return {"status": "ok", "error": None, **found}


@router.get("/recipes/{recipe_id}")
async def recipe(recipe_id: str, _: User = Depends(get_current_user)):
    try:
        return await cookidoo_service.recipe(recipe_id)
    except CookidooUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


class PlanIn(BaseModel):
    date: date
    recipe_id: str = Field(min_length=1, max_length=40)


@router.post("/plan")
async def plan(data: PlanIn, _: User = Depends(get_current_user)):
    try:
        await cookidoo_service.add(data.date, data.recipe_id)
    except CookidooUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"date": data.date.isoformat(), "recipe_id": data.recipe_id}


@router.delete("/plan/{day}/{recipe_id}")
async def unplan(day: date, recipe_id: str, _: User = Depends(get_current_user)):
    try:
        await cookidoo_service.remove(day, recipe_id)
    except CookidooUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"date": day.isoformat(), "recipe_id": recipe_id, "removed": True}


class ShoppingIn(BaseModel):
    recipe_ids: List[str] = Field(min_length=1, max_length=20)


@router.post("/shopping")
async def to_shopping(data: ShoppingIn, _: User = Depends(get_current_user)):
    """Zutaten auf die Cookidoo-Einkaufsliste (in HA als Rezept-Einkaufsliste sichtbar)."""
    try:
        return {"added": await cookidoo_service.ingredients_to_shopping(data.recipe_ids)}
    except CookidooUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
