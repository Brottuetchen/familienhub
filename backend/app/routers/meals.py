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
    recipes = {r.id: r for r in db.query(Recipe).all()}
    hub_meals_by_date = {}
    for e in entries:
        if e.date not in hub_meals_by_date:
            hub_meals_by_date[e.date] = []
        recipe = recipes.get(e.recipe_id)
        hub_meals_by_date[e.date].append({
            "id": e.id,
            "meal_type": e.meal_type,
            "recipe_id": e.recipe_id,
            "title": e.custom_title or (recipe.title if recipe else "Mahlzeit"),
            "minutes": recipe.prep_minutes if recipe else None,
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

    # Mealie: household meal plan (with recipe id, image, time)
    from app.plugins.registry import plugin_registry
    from app.services.mealie import MealieUnavailable, mealie_service

    mealie_meals_by_date = {}
    if plugin_registry.serves("meal_planning", "mealie"):
        try:
            mealie_meals_by_date = await mealie_service.plan_between(today, end)
        except MealieUnavailable as exc:
            status, error = "unavailable", str(exc)  # other entries stay visible

    # Merge nach Tagen
    days_list = []
    current = today
    while current <= end:
        date_str = current.isoformat()
        entries_for_day = (hub_meals_by_date.get(date_str, []) + cookidoo_meals_by_date.get(date_str, [])
                           + mealie_meals_by_date.get(date_str, []))
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
    recipes = {r.id: r for r in db.query(Recipe).all()}
    hub_meals_by_date = {}
    for e in entries:
        if e.date not in hub_meals_by_date:
            hub_meals_by_date[e.date] = []
        recipe = recipes.get(e.recipe_id)
        hub_meals_by_date[e.date].append({
            "id": e.id,
            "meal_type": e.meal_type,
            "recipe_id": e.recipe_id,
            "title": e.custom_title or (recipe.title if recipe else "Mahlzeit"),
            "minutes": recipe.prep_minutes if recipe else None,
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


def _collect_recipes(db: Session, days: int, start: Optional[date] = None, end: Optional[date] = None) -> List[tuple]:
    """``[(recipe title, [ingredient lines])]`` of the hub recipes planned in the range, each recipe once."""
    start, end = _range(days, start, end)
    entries = (
        db.query(MealPlanEntry)
        .filter(
            MealPlanEntry.date >= start.isoformat(),
            MealPlanEntry.date <= end.isoformat(),
            MealPlanEntry.recipe_id != None,  # noqa: E711
        )
        .all()
    )
    recipe_ids = {e.recipe_id for e in entries}
    if not recipe_ids:
        return []
    out: List[tuple] = []
    for r in db.query(Recipe).filter(Recipe.id.in_(recipe_ids)).all():
        try:
            lines = [i.strip() for i in json.loads(r.ingredients_json or "[]") if isinstance(i, str) and i.strip()]
        except (ValueError, TypeError):
            continue
        if lines:
            out.append((r.title, lines))
    return out


def _range(days: int, start: Optional[date], end: Optional[date]) -> tuple:
    """Planned days that still matter: never before today."""
    today = date.today()
    start = max(start or today, today)
    return start, max(end or (start + timedelta(days=days)), start)


async def _external_recipes(source: str, start: date, end: date) -> List[str]:
    """Recipe ids planned in Cookidoo / Mealie in the range (each once, order kept). Raises the source's error."""
    if source == "cookidoo":
        plan = await cookidoo_service.plan_between(start, end)
        key = "cookidoo_id"
    else:
        from app.services.mealie import mealie_service

        plan = await mealie_service.plan_between(start, end)
        key = "recipe_id"
    ids: List[str] = []
    for day in sorted(plan):
        for e in plan[day]:
            rid = e.get(key)
            if rid and str(rid) not in ids:
                ids.append(str(rid))
    return ids


@router.post("/shopping-list")
async def generate_shopping_list(
    days: int = 7,
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(ROLE_PARTNER)),
):
    """Ingredients of every recipe planned in the range (hub recipe book, Cookidoo, Mealie) onto the shopping list.

    One source being down never blocks the others; ``sources`` tells per source what happened.
    """
    from app.plugins.registry import plugin_registry
    from app.routers.shopping import add_recipe_ingredients, recipes_to_shopping
    from app.services.mealie import MealieUnavailable

    start_d, end_d = _range(days, start, end)
    sources: List[dict] = []

    def report(source: str, label: str, recipes: int, added: int, status: str, message: str) -> None:
        sources.append({"source": source, "label": label, "recipes": recipes, "added": added,
                        "status": status, "message": message})

    # Hub recipe book: ingredient texts go through the shopping list the hub uses (own list, Mealie or HA)
    hub_recipes = _collect_recipes(db, days, start_d, end_d)
    ingredients = list(dict.fromkeys(line for _, lines in hub_recipes for line in lines))
    hub_added = 0
    if ingredients:
        try:
            hub_added = await add_recipe_ingredients(hub_recipes, current_user.id)
        except Exception as exc:  # noqa: BLE001 – shopping backend down: report, go on
            logger.warning("Hub ingredients not added: %s", exc)
            report("hub", "Hub", len(ingredients), 0, "unavailable", "Hub: Einkaufsliste nicht erreichbar, übersprungen.")
        else:
            report("hub", "Hub", len(ingredients), hub_added, "ok",
                   f"Hub: {len(ingredients)} Zutaten, {hub_added} zur Einkaufsliste hinzugefügt." if hub_added
                   else f"Hub: {len(ingredients)} Zutaten gesammelt (keine Einkaufsliste eingerichtet).")

    external = []
    if cookidoo_plugin_active():
        external.append(("cookidoo", "Cookidoo", cookidoo_service, CookidooUnavailable))
    if plugin_registry.serves("meal_planning", "mealie"):
        from app.services.mealie import mealie_service

        external.append(("mealie", "Mealie", mealie_service, MealieUnavailable))
    for source, label, service, unavailable in external:
        try:
            ids = await _external_recipes(source, start_d, end_d)
            if not ids:
                continue
            added = await recipes_to_shopping(service, ids, current_user.id)
        except unavailable:
            report(source, label, 0, 0, "unavailable", f"{label}: nicht erreichbar, übersprungen.")
        except Exception as exc:  # noqa: BLE001 – library errors must not break the other sources
            logger.warning("%s shopping failed: %s", label, exc)
            report(source, label, 0, 0, "unavailable", f"{label}: nicht erreichbar, übersprungen.")
        else:
            report(source, label, len(ids), added, "ok", f"{label}: {len(ids)} Rezepte auf die Einkaufsliste übernommen.")

    total = sum(x["added"] for x in sources)
    if not sources:
        return {"ingredients": [], "added": 0, "sources": [], "message": "Keine Rezepte im Zeitraum geplant."}
    failed = any(x["status"] != "ok" for x in sources)
    return {
        "ingredients": ingredients,
        "added": total,
        "sources": sources,
        "message": "Einkaufsliste teilweise aktualisiert." if failed else "Einkaufsliste aktualisiert.",
    }
