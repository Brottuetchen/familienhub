"""Today-Endpunkt für schnellen App-Start."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.connectors.registry import registry
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.reminder import Reminder, visible_to
from app.models.user import User

router = APIRouter(prefix="/api", tags=["today"])
logger = logging.getLogger("hermes.today")


@router.get("/today")
async def get_today(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Kompakter Endpunkt für App-Start und Widgets.

    Liefert:
    - events: heute + morgen, max 10
    - tasks: view=mine, offen, fällig bis heute ODER mir zugewiesen, max 10
    - meals: heute
    - shopping_open: Anzahl offener Einträge
    - reminders: heute fällig
    - weather: Wetter oder null
    """
    from app.core.timeutil import local_tz

    today = datetime.now(local_tz()).date()  # Ortszeit, nicht die UTC-Uhr des Containers
    tomorrow = today + timedelta(days=1)
    today_str = today.isoformat()
    tomorrow_str = tomorrow.isoformat()

    # Events (heute + morgen, max 10), mit dem Kalenderkonto des Nutzers
    events = []
    try:
        from app.routers.calendar import collect_events

        midnight = datetime.combine(today, datetime.min.time())
        cal_events = await collect_events(db, current_user, 2, start=midnight)
        for e in (cal_events or [])[:10]:
            events.append({
                "title": e.get("title", ""),
                "start": e.get("start", ""),
                "end": e.get("end", ""),
                "all_day": e.get("all_day", False),
                "calendar": e.get("calendar", ""),
            })
    except Exception as exc:
        logger.warning("Failed to fetch events: %s", exc, exc_info=True)

    # Tasks (view=mine, offen, fällig bis heute ODER zugewiesen, max 10)
    tasks_status = "ok"
    tasks_error = None
    tasks_items = []
    try:
        from app.routers.tasks import read_tasks
        result = await read_tasks(current_user.id, db, provider="all", view="mine")

        tasks_error = result.get("error")
        if result.get("status") == "ok":
            all_tasks = result.get("items", [])
            # Filter: fällig bis heute ODER mir zugewiesen
            for task in all_tasks:
                due_str = task.get("due")
                assignee = task.get("assignee")

                # Mir zugewiesen → immer dabei
                if assignee == current_user.id:
                    tasks_items.append(task)
                # Fällig bis heute → dabei
                elif due_str:
                    try:
                        due_date = datetime.fromisoformat(due_str.replace("Z", "+00:00")).date()
                        if due_date <= today:
                            tasks_items.append(task)
                    except (ValueError, AttributeError):
                        pass

                if len(tasks_items) >= 10:
                    break
        else:
            tasks_status = result.get("status", "unavailable")
    except Exception as exc:
        logger.warning("Failed to fetch tasks: %s", exc, exc_info=True)
        tasks_status = "unavailable"

    # Meals (heute): eigene Hub-Einträge + Cookidoo
    meals = []
    try:
        from app.models.recipe import MealPlanEntry, Recipe

        titles = {r.id: r.title for r in db.query(Recipe).all()}
        for e in db.query(MealPlanEntry).filter(MealPlanEntry.date == today_str).all():
            meals.append({"source": "hub", "title": e.custom_title or titles.get(e.recipe_id, "Mahlzeit")})
    except Exception as exc:
        logger.warning("Failed to fetch hub meals: %s", exc, exc_info=True)
    ha = registry.get("homeassistant")
    # Nur HA-HTTP parallelisieren, keine Zugriffe auf die gemeinsame DB-Session.
    house_task = asyncio.create_task(ha.get_house_states()) if ha and ha.is_configured else None
    from app.services.cookidoo import CookidooUnavailable, cookidoo_service, plugin_active

    if plugin_active():
        try:
            for e in (await cookidoo_service.plan_between(today, today)).get(today_str, []):
                meals.append({"source": "cookidoo", "title": e["title"]})
        except CookidooUnavailable as exc:
            logger.warning("Cookidoo für Heute nicht erreichbar: %s", exc)
    elif ha and ha.is_configured:
        try:
            from app.config import settings
            cal_events = await ha.get_calendar_events(
                settings.ha_mealplan_calendar,
                today_str,
                today_str,
            )
            for e in cal_events:
                meals.append({
                    "source": "cookidoo",
                    "title": e.get("summary", ""),
                })
        except Exception as exc:
            logger.warning("Failed to fetch meals: %s", exc, exc_info=True)

    # Shopping (Anzahl offener Einträge)
    shopping_open = 0
    from app.routers.shopping import _hub_source

    hub_list = _hub_source()
    if hub_list:
        try:
            shopping_open = await hub_list.open_count()
        except Exception as exc:
            logger.warning("Failed to count hub shopping: %s", exc, exc_info=True)
    elif ha and ha.is_configured:
        try:
            from app.config import settings
            manual = await ha.get_todo_items(settings.ha_shopping_todo)
            recipe = await ha.get_todo_items(settings.ha_recipe_shopping_todo)
            shopping_open = sum(
                1 for item in (manual + recipe) if item.get("status") == "needs_action"
            )
        except Exception as exc:
            logger.warning("Failed to fetch shopping: %s", exc, exc_info=True)

    # Reminders (heute fällig, Tagesgrenzen in Ortszeit; gespeichert als UTC)
    reminders = []
    try:
        from app.core.timeutil import iso_z, local_tz, to_utc_naive

        start_local = datetime.combine(today, datetime.min.time()).replace(tzinfo=local_tz())
        day_start, day_end = to_utc_naive(start_local), to_utc_naive(start_local + timedelta(days=1))
        today_reminders = (
            db.query(Reminder)
            .filter(Reminder.completed == False)  # noqa: E712
            .filter(visible_to(current_user.id))
            .filter(Reminder.due_at < day_end)
            .filter(Reminder.due_at >= day_start)
            .order_by(Reminder.due_at.asc())
            .all()
        )
        for r in today_reminders:
            reminders.append({"id": r.id, "title": r.title, "due": iso_z(r.due_at)})
    except Exception as exc:
        logger.warning("Failed to fetch reminders: %s", exc, exc_info=True)

    # Weather (optional)
    weather = None
    weather_conn = registry.get("weather")
    if weather_conn:
        try:
            weather_data = await weather_conn.get_current()
            if weather_data:
                weather = weather_data
        except Exception as exc:
            logger.warning("Failed to fetch weather: %s", exc, exc_info=True)

    # Ungelesene Mitteilungen (Verlauf)
    from app.models.notification_log import NotificationLog

    unread = db.query(NotificationLog).filter(
        NotificationLog.user_id == current_user.id, NotificationLog.read_at.is_(None)
    ).count()

    return {
        "date": today_str,
        "notifications_unread": unread,
        "events": events,
        "tasks": {
            "status": tasks_status,
            "error": tasks_error,
            "items": tasks_items,
        },
        "meals": meals,
        "shopping_open": shopping_open,
        "reminders": reminders,
        "weather": weather,
        "house": await house_task if house_task else {
            "status": "not_configured", "error": None, "items": [],
        },
    }
