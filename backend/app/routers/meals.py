"""Essensplanung (Wochenplan) + automatische Einkaufsliste."""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.connectors.registry import registry
from app.core.database import get_db
from app.core.security import get_current_user, require_min_role
from app.models.recipe import MealPlanEntry, Recipe
from app.models.user import User, ROLE_PARTNER
from app.services.cookidoo import CookidooUnavailable, cookidoo_service
from app.services.cookidoo import plugin_active as cookidoo_plugin_active

router = APIRouter(prefix="/api/meals", tags=["meals"])
logger = logging.getLogger("hermes.meals")


class MealEntryRequest(BaseModel):
    date: str  # YYYY-MM-DD
    meal_type: str = "dinner"
    recipe_id: Optional[int] = None
    custom_title: Optional[str] = None


@router.get("")
async def get_meals(
    week: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Hub-Einträge + Cookidoo (read-only) im neuen Format mit week-Parameter."""
    from app.config import settings

    # Wochenberechnung
    if week:
        # YYYY-Www Format
        try:
            year, w = week.split("-W")
            today = date.fromisocalendar(int(year), int(w), 1)  # ISO-Woche, Montag
            end = today + timedelta(days=6)
        except (ValueError, AttributeError):
            raise HTTPException(400, "Ungültiges Wochenformat (erwartet YYYY-Www)")
    else:
        today = date.today()
        end = today + timedelta(days=6)

    # Hub-Einträge
    entries = (
        db.query(MealPlanEntry)
        .filter(MealPlanEntry.date >= today.isoformat(), MealPlanEntry.date <= end.isoformat())
        .order_by(MealPlanEntry.date.asc())
        .all()
    )
    recipes = {r.id: r.title for r in db.query(Recipe).all()}
    hub_meals_by_date = {}
    for e in entries:
        if e.date not in hub_meals_by_date:
            hub_meals_by_date[e.date] = []
        hub_meals_by_date[e.date].append({
            "id": e.id,
            "meal_type": e.meal_type,
            "recipe_id": e.recipe_id,
            "title": e.custom_title or recipes.get(e.recipe_id, "Mahlzeit"),
            "source": "hub",
        })

    # Cookidoo: direkt (Plugin, mit Rezept-ID/Bild/Zeit) oder lesend über den HA-Kalender
    cookidoo_meals_by_date = {}
    status, error = "ok", None
    ha = registry.get("homeassistant")
    if cookidoo_plugin_active():
        try:
            cookidoo_meals_by_date = await cookidoo_service.plan_between(today, end)
        except CookidooUnavailable as exc:
            status, error = "unavailable", str(exc)  # eigene Einträge bleiben sichtbar
    elif ha and ha.is_configured:
        try:
            events = await ha.get_calendar_events(
                settings.ha_mealplan_calendar,
                today.isoformat(),
                end.isoformat()
            )
            for e in events:
                event_date = e.get("start", {}).get("date") or e.get("start", {}).get("dateTime", "")[:10]
                if event_date not in cookidoo_meals_by_date:
                    cookidoo_meals_by_date[event_date] = []
                cookidoo_meals_by_date[event_date].append({
                    "title": e.get("summary", ""),
                    "description": e.get("description", ""),
                    "uid": e.get("uid"),
                    "source": "cookidoo",
                })
        except Exception as exc:
            logger.warning("Failed to fetch Cookidoo meals: %s", exc, exc_info=True)
            return {
                "status": "unavailable",
                "error": f"Cookidoo nicht erreichbar: {exc}",
                "days": [],
            }

    # Merge nach Tagen
    days_list = []
    current = today
    while current <= end:
        date_str = current.isoformat()
        entries_for_day = hub_meals_by_date.get(date_str, []) + cookidoo_meals_by_date.get(date_str, [])
        days_list.append({
            "date": date_str,
            "entries": entries_for_day,
        })
        current += timedelta(days=1)

    return {
        "status": status,
        "error": error,
        "days": days_list,
    }


@router.get("/plan")
async def get_plan(
    days: int = 7,
    week: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Hub-Einträge + Cookidoo (read-only) im neuen Format."""
    from app.config import settings

    # Wochenberechnung
    if week:
        # YYYY-Www Format
        try:
            year, w = week.split("-W")
            today = date.fromisocalendar(int(year), int(w), 1)  # ISO-Woche, Montag
            end = today + timedelta(days=6)
        except (ValueError, AttributeError):
            raise HTTPException(400, "Ungültiges Wochenformat (erwartet YYYY-Www)")
    else:
        today = date.today()
        end = today + timedelta(days=days - 1)

    # Hub-Einträge
    entries = (
        db.query(MealPlanEntry)
        .filter(MealPlanEntry.date >= today.isoformat(), MealPlanEntry.date <= end.isoformat())
        .order_by(MealPlanEntry.date.asc())
        .all()
    )
    recipes = {r.id: r.title for r in db.query(Recipe).all()}
    hub_meals_by_date = {}
    for e in entries:
        if e.date not in hub_meals_by_date:
            hub_meals_by_date[e.date] = []
        hub_meals_by_date[e.date].append({
            "id": e.id,
            "meal_type": e.meal_type,
            "recipe_id": e.recipe_id,
            "title": e.custom_title or recipes.get(e.recipe_id, "Mahlzeit"),
            "source": "hub",
        })

    # Cookidoo via HA
    cookidoo_meals_by_date = {}
    ha = registry.get("homeassistant")
    if ha and ha.is_configured:
        try:
            events = await ha.get_calendar_events(
                settings.ha_mealplan_calendar,
                today.isoformat(),
                end.isoformat()
            )
            for e in events:
                event_date = e.get("start", {}).get("date") or e.get("start", {}).get("dateTime", "")[:10]
                if event_date not in cookidoo_meals_by_date:
                    cookidoo_meals_by_date[event_date] = []
                cookidoo_meals_by_date[event_date].append({
                    "title": e.get("summary", ""),
                    "description": e.get("description", ""),
                    "uid": e.get("uid"),
                    "source": "cookidoo",
                })
        except Exception as exc:
            logger.warning("Failed to fetch Cookidoo meals: %s", exc, exc_info=True)
            return {
                "status": "unavailable",
                "error": f"Cookidoo nicht erreichbar: {exc}",
                "days": [],
            }

    # Merge nach Tagen
    days_list = []
    current = today
    while current <= end:
        date_str = current.isoformat()
        entries_for_day = hub_meals_by_date.get(date_str, []) + cookidoo_meals_by_date.get(date_str, [])
        days_list.append({
            "date": date_str,
            "entries": entries_for_day,
        })
        current += timedelta(days=1)

    return {
        "status": "ok",
        "error": None,
        "days": days_list,
    }


@router.post("/plan")
async def add_plan_entry(data: MealEntryRequest, db: Session = Depends(get_db), current_user: User = Depends(require_min_role(ROLE_PARTNER))):
    if not data.recipe_id and not data.custom_title:
        raise HTTPException(status_code=400, detail="recipe_id oder custom_title erforderlich")
    entry = MealPlanEntry(
        date=data.date, meal_type=data.meal_type, recipe_id=data.recipe_id, custom_title=data.custom_title
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return {"id": entry.id, "date": entry.date, "meal_type": entry.meal_type}


@router.delete("/plan/{entry_id}")
async def delete_plan_entry(entry_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_min_role(ROLE_PARTNER))):
    entry = db.query(MealPlanEntry).filter(MealPlanEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    db.delete(entry)
    db.commit()
    return {"message": "deleted"}


class MealUpdateRequest(BaseModel):
    meal_type: Optional[str] = None
    recipe_id: Optional[int] = None
    custom_title: Optional[str] = None


@router.patch("/{meal_id}")
async def update_meal(
    meal_id: str,
    data: MealUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(ROLE_PARTNER))
):
    """Aktualisiert Hub-Eintrag. Cookidoo-Einträge (Präfix cookidoo:) → 403."""
    if meal_id.startswith("cookidoo:"):
        raise HTTPException(status_code=403, detail="Cookidoo-Einträge sind schreibgeschützt")

    try:
        entry_id = int(meal_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Entry not found")

    entry = db.query(MealPlanEntry).filter(MealPlanEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    if data.meal_type is not None:
        entry.meal_type = data.meal_type
    if data.recipe_id is not None:
        entry.recipe_id = data.recipe_id
    if data.custom_title is not None:
        entry.custom_title = data.custom_title

    db.commit()
    db.refresh(entry)
    return {"id": entry.id, "date": entry.date, "meal_type": entry.meal_type}


@router.delete("/{meal_id}")
async def delete_meal(
    meal_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(ROLE_PARTNER))
):
    """Löscht Hub-Eintrag. Cookidoo-Einträge (Präfix cookidoo:) → 403."""
    if meal_id.startswith("cookidoo:"):
        raise HTTPException(status_code=403, detail="Cookidoo-Einträge sind schreibgeschützt")

    try:
        entry_id = int(meal_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Entry not found")

    entry = db.query(MealPlanEntry).filter(MealPlanEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    db.delete(entry)
    db.commit()
    return {"message": "deleted"}


def _collect_ingredients(db: Session, days: int) -> List[str]:
    today = date.today()
    end = today + timedelta(days=days)
    entries = (
        db.query(MealPlanEntry)
        .filter(
            MealPlanEntry.date >= today.isoformat(),
            MealPlanEntry.date <= end.isoformat(),
            MealPlanEntry.recipe_id != None,  # noqa: E711
        )
        .all()
    )
    recipe_ids = {e.recipe_id for e in entries}
    if not recipe_ids:
        return []
    recipes = db.query(Recipe).filter(Recipe.id.in_(recipe_ids)).all()
    seen = set()
    out: List[str] = []
    for r in recipes:
        try:
            for ing in json.loads(r.ingredients_json or "[]"):
                key = ing.strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    out.append(ing.strip())
        except (ValueError, TypeError):
            continue
    return out


@router.post("/shopping-list")
async def generate_shopping_list(days: int = 7, db: Session = Depends(get_db), current_user: User = Depends(require_min_role(ROLE_PARTNER))):
    """Sammelt Zutaten aus dem Wochenplan und legt sie in HA shopping todo."""
    from app.config import settings
    
    ingredients = _collect_ingredients(db, days)
    if not ingredients:
        return {"ingredients": [], "added": 0, "message": "Keine Rezepte im Zeitraum geplant."}

    added = 0
    ha = registry.get("homeassistant")
    if ha and ha.is_configured:
        for ing in ingredients:
            if await ha.add_todo_item(settings.ha_shopping_todo, ing):
                added += 1

    return {
        "ingredients": ingredients,
        "added": added,
        "message": f"{len(ingredients)} Zutaten gesammelt"
        + (f", {added} zur Einkaufsliste hinzugefügt." if added else " (HA nicht konfiguriert)."),
    }
