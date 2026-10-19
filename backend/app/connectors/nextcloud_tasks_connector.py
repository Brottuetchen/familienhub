"""Aufgaben-Connector über Nextcloud CalDAV (VTODO).

Pro Hub-Nutzer ein eigener CalDAV-Account.
Verwendet caldav==1.4.0.
"""

from __future__ import annotations

import asyncio
import json
from hashlib import sha256
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy.exc import IntegrityError

from app.models.task_completion import TaskCompletion
from app.services.recurrence import advance


from sqlalchemy.orm import Session

from app.config import settings
from app.connectors.base import BaseConnector
from app.core.crypto import decrypt
from app.core.database import SessionLocal
from app.core.logging_config import get_logger
from app.services import caldav_cache

logger = get_logger("connector.nextcloud_tasks")

# Alte Habitica→Nextcloud-Spiegel (habitica_nextcloud_sync.py, abgelöst durch das Habitica-Plugin)
LEGACY_HABITICA_PREFIX = "habitica-"



def _invalidates(fn):
    """A write (even a failed one may have changed something): drop the short read cache afterwards."""
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        finally:
            caldav_cache.clear_reads()

    return wrapper


def _url_key(url) -> str:
    """Comparable calendar URL: the caldav library rewrites ``calendar.url`` to ``host:443`` after a request."""
    from app.connectors.caldav_connector import _normalize_url

    return _normalize_url(str(url))


def format_due(value: Any) -> Optional[str]:
    """Due date for the app: a day as "YYYY-MM-DD", a time as ISO datetime.

    Tasks written with a time of exactly 00:00 (older hub versions, some clients) mean "on that day";
    sending them as midnight made them overdue for the whole day.
    """
    from app.core.timeutil import local_tz

    dt = getattr(value, "dt", value)
    if dt is None or dt == "":
        return None
    if isinstance(dt, str):
        return dt
    if isinstance(dt, datetime):
        local = dt.astimezone(local_tz()) if dt.tzinfo else dt
        if (local.hour, local.minute, local.second, local.microsecond) == (0, 0, 0, 0):
            return local.date().isoformat()
        return dt.isoformat()
    if isinstance(dt, date):
        return dt.isoformat()
    return str(dt)

class HouseholdUnavailable(RuntimeError):
    """Haushaltsabschluss bleibt nach einem Fachsystemfehler wiederholbar."""


class NextcloudTasksConnector(BaseConnector):
    """Nextcloud CalDAV Tasks Connector."""

    name = "nextcloud_tasks"
    display_name = "Aufgaben (Nextcloud CalDAV)"
    category = "tasks"
    icon = "✅"

    def __init__(self, user_id: Optional[int] = None):
        """Initialisiert Connector für einen bestimmten Nutzer."""
        super().__init__()
        self.user_id = user_id
        self._account = None
        self._partial = False

    @property
    def account_ref(self) -> str:
        account = self._get_account()
        if not account:
            return f"{self.user_id}:unconfigured"
        scope = json.dumps([account["url"], account["username"]]).encode()
        return f"{self.user_id}:" + sha256(scope).hexdigest()[:24]

    @property
    def is_configured(self) -> bool:
        """Prüft, ob CalDAV-Account für den Nutzer existiert."""
        if self.user_id is None:
            # Fallback: globale Konfiguration
            return bool(
                settings.caldav_url
                and settings.caldav_username
                and settings.caldav_password
            )
        return self._get_account() is not None

    def _get_account(self) -> Optional[Dict[str, str]]:
        """Holt CalDAV-Account-Daten für den Nutzer."""
        if self._account is not None:
            return self._account

        if self.user_id is None:
            # Fallback: globale Konfiguration
            if settings.caldav_url and settings.caldav_username and settings.caldav_password:
                self._account = {
                    "url": settings.caldav_url,
                    "username": settings.caldav_username,
                    "password": settings.caldav_password,
                }
                return self._account
            return None

        db = SessionLocal()
        try:
            from app.models.caldav import CalDAVAccount

            account = (
                db.query(CalDAVAccount)
                .filter(CalDAVAccount.user_id == self.user_id)
                .first()
            )
            if account:
                self._account = {
                    "url": account.url,
                    "username": account.username,
                    "password": decrypt(account.password_enc),
                }
                return self._account
        finally:
            db.close()
        return None

    async def get_lists(self) -> Dict[str, Any]:
        """Gibt alle VTODO-fähigen Kalender zurück.

        Returns:
            {"status": "ok"|"unavailable", "error": null|str, "lists": [...]}
        """
        if not self.is_configured:
            return {"status": "not_configured", "error": None, "lists": []}

        try:
            lists = await asyncio.to_thread(self._get_lists_sync)
            return {"status": "ok", "error": None, "lists": lists}
        except Exception as exc:
            logger.warning("get_lists failed: %s", exc, exc_info=True)
            return {"status": "unavailable", "error": str(exc), "lists": []}

    async def get_tasks(
        self,
        view: str = "all",
        include_done: bool = False,
    ) -> Dict[str, Any]:
        """Gibt Aufgaben zurück, gefiltert nach Ansicht.

        Args:
            view: mine | for_me | from_me | family | all
            include_done: auch erledigte Aufgaben

        Returns:
            {"status": "ok"|"unavailable", "error": null|str, "items": [...]}
        """
        if not self.is_configured:
            return {"status": "not_configured", "error": None, "items": []}

        key = ("tasks", self._account_key(), self.user_id, view, bool(include_done))
        hit = caldav_cache.read_get(key)
        if hit is not None:
            return hit
        self._partial = False
        try:
            tasks = await asyncio.to_thread(
                self._get_tasks_sync,
                view=view,
                include_done=include_done,
            )
            result = {"status": "ok", "error": None, "items": tasks}
            if not self._partial:
                caldav_cache.read_put(key, result)  # only complete, successful reads are kept
            return result
        except Exception as exc:
            logger.warning("get_tasks failed: %s", exc, exc_info=True)
            return {"status": "unavailable", "error": str(exc), "items": []}

    async def create_task(
        self,
        title: str,
        notes: Optional[str] = None,
        due: Optional[str] = None,
        priority: Optional[int] = None,
        assignee_id: Optional[int] = None,
        list_kind: Optional[str] = None,
        recurrence: str = "none",
        rotation: Optional[List[int]] = None,
        habitica: bool = False,
        created_by: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Erstellt eine neue Aufgabe.

        Args:
            title: Aufgabentitel
            notes: Notizen/Beschreibung
            due: Fälligkeitsdatum (ISO 8601)
            priority: Priorität (1=hoch, 5=mittel, 9=niedrig)
            assignee_id: Hub-User-ID des Zuständigen
            list_kind: "family" für Familie-Liste, sonst personal

        Returns:
            Task-Dict oder None bei Fehler

        Raises:
            ValueError: bei Schreibrechte-Fehler mit Format "no_write_access:ListName"
        """
        if not self.is_configured:
            return None

        try:
            task = await asyncio.to_thread(
                self._create_task_sync,
                title=title,
                notes=notes,
                due=due,
                priority=priority,
                assignee_id=assignee_id,
                list_kind=list_kind,
                recurrence=recurrence,
                rotation=rotation,
                habitica=habitica,
                created_by=created_by,
            )
            return task
        except ValueError as exc:
            # Schreibrechte-Fehler propagieren für HTTP 409
            if "no_write_access" in str(exc):
                raise
            logger.warning("create_task failed: %s", exc, exc_info=True)
            return None
        except Exception as exc:
            logger.warning("create_task failed: %s", exc, exc_info=True)
            if "403" in str(exc) or "Forbidden" in str(exc):
                raise ValueError("no_write_access:unknown")
            return None

    async def update_task(
        self, uid: str, **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Aktualisiert eine Aufgabe (nur geänderte Felder)."""
        if uid.startswith(LEGACY_HABITICA_PREFIX):
            from fastapi import HTTPException
            raise HTTPException(409, "Legacy-Habitica-Spiegel bleiben schreibgeschützt; native Aufgaben direkt auswählen")
        if not self.is_configured:
            return None

        try:
            task = await asyncio.to_thread(self._update_task_sync, uid, **kwargs)
            return task
        except (PermissionError, ValueError):
            raise
        except Exception as exc:
            logger.warning("update_task failed: %s", exc, exc_info=True)
            return None

    async def complete_task(self, uid: str) -> Optional[Dict[str, Any]]:
        """Markiert Aufgabe als erledigt."""
        if uid.startswith(LEGACY_HABITICA_PREFIX):
            from fastapi import HTTPException
            raise HTTPException(409, "Legacy-Habitica-Spiegel bleiben schreibgeschützt; native Aufgaben direkt auswählen")
        if not self.is_configured:
            return None

        try:
            task = await asyncio.to_thread(self._complete_task_sync, uid)
            return task
        except (PermissionError, HouseholdUnavailable):
            raise
        except Exception as exc:
            logger.warning("complete_task failed: %s", exc, exc_info=True)
            return None

    async def delete_task(self, uid: str) -> bool:
        """Löscht eine Aufgabe."""
        if uid.startswith(LEGACY_HABITICA_PREFIX):
            from fastapi import HTTPException
            raise HTTPException(409, "Legacy-Habitica-Spiegel bleiben schreibgeschützt; native Aufgaben direkt auswählen")
        if not self.is_configured:
            return False

        try:
            return await asyncio.to_thread(self._delete_task_sync, uid)
        except PermissionError:
            raise
        except Exception as exc:
            logger.warning("delete_task failed: %s", exc, exc_info=True)
            raise HouseholdUnavailable("Aufgabe konnte nicht gelöscht werden") from exc

    # --- Sync-Implementierung (läuft im Thread) ---

    def _get_client(self):
        """The account's shared CalDAV client."""
        account = self._get_account()
        if not account:
            raise ValueError("No CalDAV account configured")
        return caldav_cache.client_for(account["url"], account["username"], account["password"])

    def _account_key(self) -> str:
        account = self._get_account() or {}
        return caldav_cache.account_key(account.get("url"), account.get("username"), account.get("password"))

    def _get_vtodo_calendars(self, failed_urls: Optional[set[str]] = None):
        """Only the calendars that support VTODO (calendar list and components come from the shared cache)."""
        account = self._get_account()
        if not account:
            raise ValueError("No CalDAV account configured")
        vtodo_calendars = []
        for info in caldav_cache.calendars(account["url"], account["username"], account["password"]):
            supported = info.supports("VTODO")
            if supported is None:
                logger.debug("Failed to check calendar components for %s", info.url)
                if failed_urls is not None:
                    failed_urls.add(_url_key(info.url))
                continue
            if supported:
                vtodo_calendars.append(info.cal)
        return vtodo_calendars

    def _get_task_lists_config(self, db: Session) -> List[Any]:
        """Holt TaskList-Konfiguration für den Nutzer."""
        from app.models.caldav import TaskList

        return (
            db.query(TaskList)
            .filter(TaskList.user_id == self.user_id)
            .all()
        )

    def _get_lists_sync(self) -> List[Dict[str, Any]]:
        """Gibt VTODO-Kalender zurück."""
        calendars = self._get_vtodo_calendars()
        result = []

        for cal in calendars:
            result.append({
                "caldav_url": str(cal.url),
                "display_name": cal.name or "Unbenannt",
            })

        return result

    def _get_tasks_sync(
        self, view: str = "all", include_done: bool = False
    ) -> List[Dict[str, Any]]:
        """Liest Aufgaben aus CalDAV."""

        db = SessionLocal()
        try:
            task_lists = self._get_task_lists_config(db)
            if not task_lists:
                return []

            # Map: caldav_url -> TaskList
            list_map = {_url_key(tl.caldav_url): tl for tl in task_lists}

            calendars = self._get_vtodo_calendars()
            results = []

            for cal in calendars:
                cal_url = _url_key(cal.url)
                if cal_url not in list_map:
                    continue

                task_list = list_map[cal_url]

                # Filter nach view
                # "mine"/"for_me" nur aus der EIGENEN privaten Liste. Geteilte private Listen
                # anderer (für Zuweisungen nötig) gehören nicht dazu.
                own_personal = task_list.kind == "personal" and task_list.owner_user_id == self.user_id
                family_list = task_list.kind == "family"
                # Family-list tasks assigned to me (also the rotation's current turn) count as mine as well
                if view in ("mine", "for_me") and not (own_personal or family_list):
                    continue
                if view == "from_me" and task_list.kind == "personal" and task_list.owner_user_id == self.user_id:
                    continue
                if view == "family" and task_list.kind != "family":
                    continue
                if view == "all" and task_list.kind == "hidden":
                    continue

                try:
                    todos = cal.todos(include_completed=include_done)
                    for todo in todos:
                        try:
                            comp = todo.icalendar_component
                            task = self._vtodo_to_dict(comp, task_list)
                            if task.get("uid", "").startswith(LEGACY_HABITICA_PREFIX):
                                continue  # Spiegel des alten Habitica-Skripts; Habitica kommt nativ übers Plugin

                            # View-Filter nach created_by
                            assigned_to_me = task.get("assignee") == self.user_id
                            if view == "mine":
                                # Everything I have to do: my own list (also from others) and family tasks for me
                                if not own_personal and not assigned_to_me:
                                    continue
                            elif view == "for_me":
                                # Given to me by someone else: in my list, or a family task assigned to me
                                created_by = task.get("created_by")
                                if not created_by or created_by == self.user_id:
                                    continue
                                if not own_personal and not assigned_to_me:
                                    continue
                            elif view == "from_me":
                                # Given by me to someone else (not what I assigned to myself)
                                created_by = task.get("created_by")
                                if created_by != self.user_id or assigned_to_me:
                                    continue

                            results.append(task)
                        except Exception as exc:
                            logger.debug("Failed to parse VTODO: %s", exc)
                            continue
                except Exception as exc:
                    logger.debug("Failed to fetch todos from calendar: %s", exc)
                    self._partial = True  # an incomplete answer must not be kept in the read cache
                    continue

            return results
        finally:
            db.close()

    @_invalidates
    def _create_task_sync(
        self,
        title: str,
        notes: Optional[str] = None,
        due: Optional[str] = None,
        priority: Optional[int] = None,
        assignee_id: Optional[int] = None,
        list_kind: Optional[str] = None,
        recurrence: str = "none",
        rotation: Optional[List[int]] = None,
        habitica: bool = False,
        created_by: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Erstellt VTODO. ``created_by``: the person who assigned the task (this account belongs to the recipient)."""
        from icalendar import Calendar, Todo

        db = SessionLocal()
        try:
            task_lists = self._get_task_lists_config(db)
            if not task_lists:
                return None

            # Ziel-Liste bestimmen
            target_list = None
            if list_kind == "family":
                # Familie-Liste
                for tl in task_lists:
                    if tl.kind == "family":
                        target_list = tl
                        break
            elif assignee_id and assignee_id != self.user_id:
                # Für andere Person: deren personal-Liste
                for tl in task_lists:
                    if tl.kind == "personal" and tl.owner_user_id == assignee_id:
                        target_list = tl
                        break
            else:
                # Eigene personal-Liste
                for tl in task_lists:
                    if tl.kind == "personal" and tl.owner_user_id == self.user_id:
                        target_list = tl
                        break

            if not target_list:
                logger.warning("No suitable task list found")
                return None

            # Finde entsprechenden Kalender
            calendars = self._get_vtodo_calendars()
            target_cal = None
            for cal in calendars:
                if _url_key(cal.url) == _url_key(target_list.caldav_url):
                    target_cal = cal
                    break

            if not target_cal:
                logger.warning("Calendar not found: %s", target_list.caldav_url)
                return None

            # VTODO bauen
            cal = Calendar()
            cal.add("prodid", "-//Familienhub//NONSGML Tasks//EN")
            cal.add("version", "2.0")

            todo = Todo()
            uid = str(uuid4())
            todo.add("uid", uid)
            todo.add("created", datetime.utcnow())
            todo.add("dtstamp", datetime.utcnow())
            todo.add("summary", title)
            todo.add("status", "NEEDS-ACTION")

            if notes:
                todo.add("description", notes)
            if due:
                # Parse ISO 8601
                from dateutil import parser as dateparser
                due_dt = dateparser.parse(due)
                if len(due) == 10:
                    due_dt = date.fromisoformat(due)  # due on a day: DUE;VALUE=DATE, not midnight
                elif rotation:
                    from app.core.timeutil import local_tz
                    due_dt = due_dt.astimezone(local_tz()) if due_dt.tzinfo else due_dt.replace(tzinfo=local_tz())
                todo.add("due", due_dt)
            if priority is not None:
                todo.add("priority", int(priority))

            # X-Properties
            if created_by or self.user_id:
                todo.add("x-familienhub-created-by", str(created_by or self.user_id))
            if assignee_id:
                todo.add("x-familienhub-assignee", str(assignee_id))

            if rotation:
                todo.add("x-familienhub-recurrence", recurrence)
                todo.add("x-familienhub-rotation", ",".join(map(str, rotation)))
                todo.add("x-familienhub-habitica", "1" if habitica else "0")

            cal.add_component(todo)
            ical_str = cal.to_ical().decode("utf-8")

            # Speichern
            try:
                new_todo = target_cal.save_todo(ical=ical_str)
                comp = new_todo.icalendar_component
                return self._vtodo_to_dict(comp, target_list)
            except Exception as exc:
                if "403" in str(exc) or "Forbidden" in str(exc):
                    raise ValueError(f"no_write_access:{target_list.display_name}")
                raise

        finally:
            db.close()

    @_invalidates
    def _update_task_sync(
        self, uid: str, **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Aktualisiert VTODO, erhält unbekannte Properties."""

        db = SessionLocal()
        try:
            task_lists = self._get_task_lists_config(db)
            if not task_lists:
                return None

            list_map = {_url_key(tl.caldav_url): tl for tl in task_lists}
            calendars = self._get_vtodo_calendars()

            # Finde Todo
            for cal in calendars:
                if _url_key(cal.url) not in list_map:
                    continue

                try:
                    todo = cal.todo_by_uid(uid)
                    if todo:
                        comp = todo.icalendar_component

                        task = self._vtodo_to_dict(comp, list_map[_url_key(cal.url)])
                        self._check_household_access(db, list_map[_url_key(cal.url)], task, manage=True)
                        if task["rotation"]:
                            title = kwargs.get("title", task["title"])
                            due = kwargs.get("due", task["due"])
                            if not title.strip() or len(title) > 200 or not due:
                                raise ValueError("Haushalt benötigt Titel (1–200 Zeichen) und Fälligkeit")
                            datetime.fromisoformat(due.replace("Z", "+00:00"))
                        # Nur geänderte Felder aktualisieren
                        if "title" in kwargs:
                            comp["summary"] = kwargs["title"]
                        if "notes" in kwargs:
                            comp["description"] = kwargs["notes"]
                        if "due" in kwargs:
                            if kwargs["due"]:
                                from dateutil import parser as dateparser
                                due = kwargs["due"]
                                due_dt = dateparser.parse(due)
                                if len(due) == 10:
                                    due_dt = date.fromisoformat(due)  # due on a day, not at midnight
                                elif task["rotation"]:
                                    from app.core.timeutil import local_tz
                                    due_dt = (due_dt.astimezone(local_tz()) if due_dt.tzinfo else
                                              due_dt.replace(tzinfo=local_tz()))
                                comp.pop("due", None)
                                comp.add("due", due_dt)
                            else:
                                if "due" in comp:
                                    del comp["due"]
                        if "priority" in kwargs and kwargs["priority"] is not None:
                            comp["priority"] = int(kwargs["priority"])
                        if "done" in kwargs:
                            if kwargs["done"]:
                                from datetime import timezone
                                for name in ("status", "completed", "percent-complete"):
                                    comp.pop(name, None)
                                comp.add("status", "COMPLETED")
                                comp.add("completed", datetime.now(timezone.utc))
                                comp.add("percent-complete", 100)
                            else:
                                comp["status"] = "NEEDS-ACTION"
                                if "completed" in comp:
                                    del comp["completed"]
                                if "percent-complete" in comp:
                                    del comp["percent-complete"]

                        # Speichern
                        todo.save()

                        # Neu laden
                        saved_todo = cal.todo_by_uid(uid)
                        if saved_todo:
                            saved_comp = saved_todo.icalendar_component
                            task_list = list_map[_url_key(cal.url)]
                            return self._vtodo_to_dict(saved_comp, task_list)

                except (PermissionError, ValueError):
                    raise
                except Exception as exc:
                    logger.debug("Failed to update in calendar %s: %s", cal.url, exc)
                    continue

            return None
        finally:
            db.close()

    @_invalidates
    def _complete_task_sync(self, uid: str) -> Optional[Dict[str, Any]]:
        """Markiert Aufgabe als erledigt mit todo.complete()."""
        db = SessionLocal()
        try:
            task_lists = self._get_task_lists_config(db)
            if not task_lists:
                return None

            list_map = {_url_key(tl.caldav_url): tl for tl in task_lists}
            calendars = self._get_vtodo_calendars()

            for cal in calendars:
                if _url_key(cal.url) not in list_map:
                    continue

                try:
                    todo = cal.todo_by_uid(uid)
                    if todo:
                        comp = todo.icalendar_component
                        task_list = list_map[_url_key(cal.url)]
                        task = self._vtodo_to_dict(comp, task_list)
                        if task["rotation"]:
                            try:
                                return self._complete_household(db, cal, todo, task_list, task)
                            except PermissionError:
                                raise
                            except Exception as exc:
                                logger.warning("Haushaltsabschluss fehlgeschlagen", exc_info=True)
                                raise HouseholdUnavailable("Haushaltsaufgabe konnte nicht abgeschlossen werden") from exc
                        # caldav 1.4.0 hat todo.complete()
                        todo.complete()

                        # Neu laden
                        completed_todo = cal.todo_by_uid(uid)
                        if completed_todo:
                            comp = completed_todo.icalendar_component
                            task_list = list_map[_url_key(cal.url)]
                            return self._vtodo_to_dict(comp, task_list)
                except (PermissionError, HouseholdUnavailable):
                    raise
                except Exception as exc:
                    logger.debug("Failed to complete in calendar %s: %s", cal.url, exc)
                    continue

            return None
        finally:
            db.close()

    def _check_household_access(self, db, task_list, task, manage=False):
        from app.models.user import User

        if not task["rotation"]:
            return
        user = db.get(User, self.user_id)
        if task_list.kind != "family" or not user or user.role == "guest" or (
            user.role not in ("admin", "partner") and (manage or task["assignee"] != user.id)
        ):
            raise PermissionError("Diese Haushaltsaufgabe darfst du nicht ändern")

    def _complete_household(self, db, calendar, todo, task_list, task):
        """Ein Abschlussbeleg serialisiert parallele Abschlüsse auch über Worker hinweg."""
        from copy import deepcopy
        from icalendar import Calendar
        from caldav.lib.error import NotFoundError
        from app.models.user import User

        self._check_household_access(db, task_list, task)
        key = {"uid": task["uid"]}
        if db.get(TaskCompletion, key):
            task["done"] = True
            task["_score"] = False
            return task
        try:
            db.add(TaskCompletion(**key))
            db.flush()  # Unique-Key wartet auf den ersten Abschluss, kein Prozess-Lock.
        except IntegrityError:
            db.rollback()
            task["done"], task["_score"] = True, False
            return task
        successor_uid = str(uuid5(NAMESPACE_URL, f"familienhub/{task['uid']}/next"))
        try:
            successor = calendar.todo_by_uid(successor_uid)
        except NotFoundError:
            successor = None
        if not successor:
            component = deepcopy(todo.icalendar_component)
            due = component.get("due")
            nxt = advance(due.dt if due else None, task["recurrence"])
            if nxt is None:
                raise ValueError("Ungültige Wiederholung oder fehlende Fälligkeit")
            rotation = task["rotation"]
            start = rotation.index(task["assignee"]) if task["assignee"] in rotation else -1
            active = {u.id for u in db.query(User).filter(User.is_active == True, User.role != "guest")}  # noqa: E712
            assignee = next((rotation[(start + offset) % len(rotation)]
                             for offset in range(1, len(rotation) + 1)
                             if rotation[(start + offset) % len(rotation)] in active), None)
            if assignee is None:
                raise ValueError("Keine aktive Person in der Rotation")
            for prop in ("uid", "due", "status", "completed", "percent-complete", "x-familienhub-assignee"):
                component.pop(prop, None)
            component.add("uid", successor_uid)
            component.add("due", nxt)
            component.add("status", "NEEDS-ACTION")
            component.add("x-familienhub-assignee", str(assignee))
            ical = Calendar()
            ical.add("version", "2.0")
            ical.add("prodid", "-//Familienhub//NONSGML Tasks//EN")
            ical.add_component(component)
            # Stabiler UID: Wiederholung nach Netz-/DB-Fehler überschreibt keinen anderen Termin.
            calendar.save_todo(ical=ical.to_ical().decode("utf-8"))
        todo.complete()
        db.commit()
        result = self._vtodo_to_dict(todo.icalendar_component, task_list)
        result["_score"] = task["habitica"]
        return result

    @_invalidates
    def _delete_task_sync(self, uid: str) -> bool:
        """Löscht VTODO."""
        from caldav.lib.error import NotFoundError

        db = SessionLocal()
        try:
            task_lists = self._get_task_lists_config(db)
            if not task_lists:
                return False

            list_map = {_url_key(tl.caldav_url): tl for tl in task_lists}
            failed_urls: set[str] = set()
            calendars = self._get_vtodo_calendars(failed_urls)

            for cal in calendars:
                if _url_key(cal.url) not in list_map:
                    continue

                try:
                    todo = cal.todo_by_uid(uid)
                except NotFoundError:
                    continue
                if todo:
                    self._check_household_access(db, list_map[_url_key(cal.url)],
                        self._vtodo_to_dict(todo.icalendar_component, list_map[_url_key(cal.url)]), manage=True)
                    try:
                        todo.delete()
                    except PermissionError as exc:
                        # Fachsystem-Schreibrecht ist kein Hub-Rollenverbot.
                        raise HouseholdUnavailable("Aufgabe konnte nicht gelöscht werden") from exc
                    return True
            if failed_urls.intersection(list_map):
                raise HouseholdUnavailable("Aufgabenlisten konnten nicht vollständig geprüft werden")
            return False
        finally:
            db.close()

    def _vtodo_to_dict(self, component: Any, task_list: Any) -> Dict[str, Any]:
        """VTODO-Komponente zu Task-Dict."""
        created_by_raw = component.get("x-familienhub-created-by")
        assignee_raw = component.get("x-familienhub-assignee")

        created_by = None
        if created_by_raw:
            try:
                created_by = int(str(created_by_raw))
            except (ValueError, TypeError):
                pass

        assignee = None
        if assignee_raw:
            try:
                assignee = int(str(assignee_raw))
            except (ValueError, TypeError):
                pass

        rotation_raw = str(component.get("x-familienhub-rotation", ""))
        rotation = [int(v) for v in rotation_raw.split(",") if v.isdecimal()]
        return {
            "rotation": rotation,
            "recurrence": str(component.get("x-familienhub-recurrence", "none")),
            "habitica": str(component.get("x-familienhub-habitica", "0")) == "1",
            "uid": str(component.get("uid", "")),
            "title": str(component.get("summary", "Aufgabe")),
            "notes": str(component.get("description", "") or ""),
            "due": format_due(component.get("due")),
            "priority": int(component.get("priority", 0)) if component.get("priority") else None,
            "done": str(component.get("status", "")).upper() == "COMPLETED",
            "list": {
                "name": task_list.display_name,
                "kind": task_list.kind,
            },
            "created_by": created_by,
            "assignee": assignee,
            "etag": None,  # TODO: ETag aus todo-Objekt wenn nötig
        }

    @staticmethod
    def _format_date(value: Any) -> Optional[str]:
        """Datum formatieren."""
        if not value:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, datetime):
            return value.isoformat()
        if hasattr(value, "dt"):
            dt = value.dt
            if isinstance(dt, datetime):
                return dt.isoformat()
            if hasattr(dt, "isoformat"):
                return dt.isoformat()
        return str(value)
