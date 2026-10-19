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
from app.core.timing import timed
from app.models.reminder import Reminder, visible_to
from app.models.user import User

router = APIRouter(prefix="/api", tags=["today"])
logger = logging.getLogger("hermes.today")

# Seconds a source may take before "Heute" shows its fail-soft state instead of waiting (#71)
SOURCE_TIMEOUT = {"events": 8.0, "tasks": 8.0, "meals": 6.0, "shopping": 5.0, "reminders": 3.0, "weather": 4.0, "house": 6.0}


def _occurs_on(event: dict, day) -> bool:
    """Does the event touch ``day``? All-day ends are exclusive; a timed end at 00:00 belongs to the day before."""
    def parse(raw):
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None

    start = parse(event.get("start"))
    if start is None:
        return False
    end = parse(event.get("end")) or start
    first = start.date()
    if event.get("all_day"):
        return first <= day and (day < end.date() or first == day)
    last = end.date()
    if end.time() == datetime.min.time() and last > first:
        last -= timedelta(days=1)
    return first <= day <= last


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
    today_str = today.isoformat()
    ha = registry.get("homeassistant")

    async def events_part():
        events = []
        try:
            from app.routers.calendar import collect_events

            midnight = datetime.combine(today, datetime.min.time())
            cal_events = await collect_events(db, current_user, 2, start=midnight)
            # The window also reaches into tomorrow (so late events are never cut off); the card says "today".
            for e in [e for e in (cal_events or []) if _occurs_on(e, today)][:10]:
                events.append({
                    "title": e.get("title", ""),
                    "start": e.get("start", ""),
                    "end": e.get("end", ""),
                    "all_day": e.get("all_day", False),
                    "calendar": e.get("calendar", ""),
                })
        except Exception as exc:
            logger.warning("Failed to fetch events: %s", exc, exc_info=True)
        return events

    async def tasks_part():
        """View=mine, open, due until today OR assigned to me, max 10."""
        tasks_status, tasks_error, tasks_items = "ok", None, []
        try:
            from app.routers.tasks import read_tasks

            result = await read_tasks(current_user.id, db, provider="all", view="mine")
            tasks_error = result.get("error")
            if result.get("status") == "ok":
                for task in result.get("items", []):
                    due_str = task.get("due")
                    if task.get("assignee") == current_user.id:
                        tasks_items.append(task)
                    elif due_str:
                        try:
                            if datetime.fromisoformat(due_str.replace("Z", "+00:00")).date() <= today:
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
        return {"status": tasks_status, "error": tasks_error, "items": tasks_items}

    async def meals_part():
        meals = []
        try:
            from app.models.recipe import MealPlanEntry, Recipe

            titles = {r.id: r.title for r in db.query(Recipe).all()}
            for e in db.query(MealPlanEntry).filter(MealPlanEntry.date == today_str).all():
                meals.append({"source": "hub", "title": e.custom_title or titles.get(e.recipe_id, "Mahlzeit")})
        except Exception as exc:
            logger.warning("Failed to fetch hub meals: %s", exc, exc_info=True)
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

                cal_events = await ha.get_calendar_events(settings.ha_mealplan_calendar, today_str, today_str)
                for e in cal_events:
                    meals.append({"source": "cookidoo", "title": e.get("summary", "")})
            except Exception as exc:
                logger.warning("Failed to fetch meals: %s", exc, exc_info=True)
        return meals

    async def shopping_part():
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
                shopping_open = sum(1 for item in (manual + recipe) if item.get("status") == "needs_action")
            except Exception as exc:
                logger.warning("Failed to fetch shopping: %s", exc, exc_info=True)
        return shopping_open

    async def reminders_part():
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
        return reminders

    async def weather_part():
        weather_conn = registry.get("weather")
        if weather_conn:
            try:
                return await weather_conn.get_current() or None
            except Exception as exc:
                logger.warning("Failed to fetch weather: %s", exc, exc_info=True)
        return None

    async def house_part():
        if ha and ha.is_configured:
            return await ha.get_house_states()
        return {"status": "not_configured", "error": None, "items": []}

    gone = {"status": "unavailable", "error": "Zeitüberschreitung", "items": []}

    def limited(name, make, default, on_timeout=None):
        return timed(name, make, timeout=SOURCE_TIMEOUT[name], default=default, logger=logger, on_timeout=on_timeout)

    # All sources at once: the page takes as long as the slowest one, not the sum. They share the request's
    # DB session, but its (synchronous) queries never overlap on the event loop.
    events, tasks, meals, shopping_open, reminders, weather, house = await asyncio.gather(
        limited("events", events_part, []),
        limited("tasks", tasks_part, None, on_timeout=lambda: dict(gone)),
        limited("meals", meals_part, []),
        limited("shopping", shopping_part, 0),
        limited("reminders", reminders_part, []),
        limited("weather", weather_part, None),
        limited("house", house_part, None, on_timeout=lambda: dict(gone)),
    )

    # Ungelesene Mitteilungen (Verlauf)
    from app.models.notification_log import NotificationLog

    unread = db.query(NotificationLog).filter(
        NotificationLog.user_id == current_user.id, NotificationLog.read_at.is_(None)
    ).count()

    return {
        "date": today_str,
        "notifications_unread": unread,
        "events": events,
        "tasks": tasks,
        "meals": meals,
        "shopping_open": shopping_open,
        "reminders": reminders,
        "weather": weather,
        "house": house,
    }
