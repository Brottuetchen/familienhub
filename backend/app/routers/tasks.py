"""Router für Aufgaben (CalDAV/Nextcloud Tasks)."""

from __future__ import annotations

import ipaddress
import logging
import uuid
from typing import List, Literal, Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, StrictInt, field_validator, model_validator
from sqlalchemy.orm import Session

from app.core.crypto import encrypt
from app.core.database import get_db
from app.core.security import get_current_user, require_min_role
from app.models.caldav import CalDAVAccount, TaskList
from app.models.user import User, ROLE_CHILD, ROLE_PARTNER
from app.schemas import CanonicalUUID
from app.plugins.registry import plugin_registry

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
logger = logging.getLogger("hermes.tasks")


def validate_caldav_url(url: str) -> str:
    """Schutz vor SSRF: Der Hub ruft diese Adresse mit den Zugangsdaten der Person ab.

    Ist CALDAV_URL (Nextcloud-Plugin) gesetzt, sind nur Adressen auf genau diesem Server erlaubt.
    Sonst nur https auf einen Hostnamen: keine IP-Adressen, kein localhost, keine Zugangsdaten,
    keine Query/Fragmente.
    """
    from app.plugins.base import get_setting

    parts = urlsplit(url.strip())
    try:
        port = parts.port
    except ValueError:
        raise ValueError("Ungültige CalDAV-Adresse")
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not host or parts.username or parts.password \
            or parts.query or parts.fragment:
        raise ValueError("Ungültige CalDAV-Adresse")
    pinned = str(get_setting("CALDAV_URL") or "").strip()
    if pinned:
        ref = urlsplit(pinned)
        if (parts.scheme, host, port or None) != (ref.scheme, (ref.hostname or "").lower(), ref.port or None):
            raise ValueError("CalDAV-Adresse muss auf dem eingerichteten Nextcloud-Server liegen")
        return url.strip()
    if parts.scheme != "https":
        raise ValueError("CalDAV-Adresse muss https verwenden")
    try:
        ipaddress.ip_address(host.strip("[]"))
        is_ip = True
    except ValueError:
        is_ip = False
    if is_ip:
        raise ValueError("CalDAV-Adresse muss einen Hostnamen verwenden, keine IP-Adresse")
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("CalDAV-Adresse darf nicht auf den Hub selbst zeigen")
    return url.strip()




def context_task(task, provider, connector):
    if isinstance(task, dict):
        return {**task, "provider": provider, "account": connector.account_ref}
    return task


@router.get("/providers")
def task_providers(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = []
    for plugin in plugin_registry.providers("tasks"):
        try:
            connector = plugin.task_connector(current_user.id, db)
            items.append({"id": plugin.id, "name": plugin.name, "account": connector.account_ref,
                          "configured": connector.is_configured})
        except Exception:
            from app.core.logging_config import get_logger
            get_logger("router.tasks").warning("Aufgabenanbieter nicht bereit: %s", plugin.id, exc_info=True)
            items.append({"id": plugin.id, "name": plugin.name, "account": "", "configured": False, "status": "unavailable"})
    return {"items": items}


async def read_tasks(user_id, db, provider="all", account=None, view="all", include_done=False):
    plugins = plugin_registry.providers("tasks") if provider == "all" else [plugin_registry.get(provider)]
    if provider == "all" and account is not None:
        raise HTTPException(422, "Eine Kontoreferenz erfordert einen ausdrücklich gewählten Anbieter")
    items, statuses = [], {}
    for plugin in plugins:
        name = plugin.id if plugin else provider
        connector = None
        try:
            connector = plugin_registry.task_connector(name, user_id, db, account, implicit=provider == "all")
            result = await connector.get_tasks(view=view, include_done=include_done)
        except Exception as exc:
            if provider != "all" and isinstance(exc, HTTPException):
                raise
            from app.core.logging_config import get_logger
            get_logger("router.tasks").warning("Aufgabenanbieter nicht erreichbar: %s", name, exc_info=True)
            result = {"status": "unavailable", "error": "Aufgabenanbieter nicht erreichbar", "items": []}
        statuses[name] = {"status": result["status"], "error": result.get("error")}
        items.extend(context_task(t, name, connector) for t in result.get("items", []))
    if view == "from_me" and provider == "all":
        # Tasks given to others that live in the recipient's own provider (#38); status read via her connector
        from app.services import task_routing

        try:
            seen = {(t.get("provider"), t.get("uid")) for t in items if isinstance(t, dict)}
            items.extend(await task_routing.assigned_items(user_id, db, include_done, skip=seen))
        except Exception:  # noqa: BLE001 - never an exception into the UI
            logger.warning("Zugewiesene Aufgaben nicht lesbar", exc_info=True)
    state = "ok" if items or any(s["status"] == "ok" for s in statuses.values()) else (
        "unavailable" if any(s["status"] == "unavailable" for s in statuses.values()) else "not_configured")
    return {"status": state, "error": next((s["error"] for s in statuses.values() if s["error"]), None),
            "items": items, "providers": statuses}


# --- Request/Response Models ---


class TaskCreateRequest(BaseModel):
    """Neue Aufgabe erstellen."""

    title: str
    notes: Optional[str] = None
    due: Optional[str] = None
    priority: Optional[int] = None
    assignee_id: Optional[int] = None
    list: Optional[str] = None  # "family" oder None
    recurrence: str = "none"
    rotation: List[StrictInt] = Field(default_factory=lambda: [], max_length=50)
    habitica: bool = False
    native: dict | None = None
    operation_id: CanonicalUUID | None = None

    @model_validator(mode="after")
    def validate_household(self):
        from datetime import datetime
        from app.services.recurrence import VALID_RECURRENCE

        if self.rotation or self.recurrence != "none" or self.habitica:
            if (self.list != "family" or not self.rotation or
                self.recurrence not in VALID_RECURRENCE - {"none"} or
                len(set(self.rotation)) != len(self.rotation) or
                any(uid <= 0 for uid in self.rotation) or
                not self.title.strip() or len(self.title) > 200 or
                self.assignee_id not in (None, self.rotation[0])):
                raise ValueError("Haushalt benötigt Familienliste, Titel und eindeutige Rotation")
            if not self.due:
                raise ValueError("Haushalt benötigt eine Fälligkeit")
            datetime.fromisoformat(self.due.replace("Z", "+00:00"))
        return self


class TaskUpdateRequest(BaseModel):
    """Aufgabe aktualisieren."""

    title: Optional[str] = None
    notes: Optional[str] = None
    due: Optional[str] = None
    priority: Optional[int] = None
    native: dict | None = None
    expected_version: str | None = None
    operation_id: CanonicalUUID | None = None


class CalDAVAccountRequest(BaseModel):
    """CalDAV-Account-Daten."""

    url: str = Field(max_length=500)
    username: str = Field(max_length=200)
    password: str = Field(max_length=500)

    @field_validator("url")
    @classmethod
    def _safe_url(cls, value: str) -> str:
        return validate_caldav_url(value)


class CalDAVAccountResponse(BaseModel):
    """CalDAV-Account-Antwort (ohne Passwort)."""

    url: str
    username: str
    has_password: bool


class TaskListConfigRequest(BaseModel):
    """Task-Listen-Konfiguration."""

    caldav_url: str = Field(max_length=500)
    kind: Literal["personal", "family", "hidden"]
    owner_user_id: Optional[int] = None


# --- Endpunkte ---


@router.get("/lists")
async def get_task_lists(
    provider: str = "nextcloud",
    account: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Gibt alle VTODO-fähigen CalDAV-Kalender zurück."""

    connector = plugin_registry.task_connector(provider, current_user.id, db, account)
    result = await connector.get_lists()
    return {**result, "provider": provider, "account": connector.account_ref,
            "lists": [{**entry, "provider": provider, "account": connector.account_ref} for entry in result.get("lists", [])]}


@router.get("")
async def get_tasks(
    view: str = "all",
    include_done: bool = False,
    provider: str = "nextcloud",
    account: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Gibt Aufgaben zurück, gefiltert nach Ansicht.

    Args:
        view: mine | for_me | from_me | family | all
        include_done: auch erledigte Aufgaben
    """

    return await read_tasks(current_user.id, db, provider, account, view, include_done)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_task(
    task: TaskCreateRequest,
    provider: str = "nextcloud",
    account: str | None = None,
    current_user: User = Depends(require_min_role(ROLE_PARTNER)),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    """Erstellt eine neue Aufgabe. Mit Idempotency-Key (Offline-Warteschlange) höchstens einmal."""
    from app.services import idempotency

    return await idempotency.run(
        current_user.id, f"tasks:create:{provider}:{account or ''}", idempotency_key,
        lambda: _create_task(task, provider, account, current_user, db))


def _validate_people(task: TaskCreateRequest, current_user: User, db: Session):
    """Rotation members and the assignee must be active family members. Returns the assignee (or None)."""
    if task.rotation:
        if current_user.role not in ("admin", "partner"):
            raise HTTPException(status_code=403, detail="Nur Erwachsene verwalten Haushaltsaufgaben")
        eligible = {u.id for u in db.query(User).filter(User.id.in_(task.rotation),
                    User.is_active == True, User.role != "guest")}  # noqa: E712
        if eligible != set(task.rotation):
            raise HTTPException(status_code=422, detail="Rotation enthält ungültige Personen")

    if task.assignee_id is not None and not task.rotation:
        assignee = db.query(User).filter(User.id == task.assignee_id, User.is_active == True,  # noqa: E712
                                         User.role != "guest").first()
        if assignee is None:
            raise HTTPException(status_code=422, detail="Zuweisung nur an aktive Familienmitglieder")
        return assignee
    return None


async def _notify_assigned(task: TaskCreateRequest, current_user: User, assignee_id: int | None, uid: str):
    from app.services.notify import notify

    if assignee_id and assignee_id != current_user.id:
        try:
            await notify(
                user_id=assignee_id,
                title="Neue Aufgabe zugewiesen",
                body=f"{current_user.full_name or current_user.username}: {task.title}",
                data={"task_uid": uid, "route": "/tasks?view=for_me"},
                category="task_assigned",
            )
        except Exception:
            # Fehler bei Benachrichtigung blockiert nicht die Erstellung
            pass


async def _create_task(task: TaskCreateRequest, provider: str, account: str | None, current_user: User, db: Session):
    """Erstellt eine neue Aufgabe; ``provider=auto`` routet nach Empfänger bzw. Familienliste (#38)."""
    if provider == "auto":
        return await _create_task_auto(task, current_user, db)
    return await _create_task_in(task, provider, account, current_user, db)


async def _create_task_auto(task: TaskCreateRequest, current_user: User, db: Session):
    """Where the task lands is not the creator's decision.

    - family list / household rotation: first source of the area that can hold a family list, else the hub
    - task for another person: that person's preferred place, written with *her own* account; else the hub
    - own task: the creator's own preferred place; else the hub
    """
    from app.services import task_routing

    assignee = _validate_people(task, current_user, db)
    family = bool(task.rotation) or task.list == "family"

    if assignee is not None and assignee.id != current_user.id and not family:
        placed = await task_routing.create_for_recipient(
            current_user, assignee, db, title=task.title, notes=task.notes, due=task.due, priority=task.priority,
            native=task.native)
        if placed is None:
            raise HTTPException(status_code=409, detail="Kein Aufgabenort verfügbar")
        result, connector, row, plugin = placed
        await _notify_assigned(task, current_user, assignee.id, str(result["uid"]))
        info = {"provider": plugin.id, "fallback": bool(row.fallback), "recipient": assignee.id}
        if plugin.fallback:  # hub task: the creator can open and edit it like any other hub task
            mine = plugin.task_connector(current_user.id, db)
            return {**context_task(result, plugin.id, mine), "placed": info}
        return {**task_routing.to_item(row), "placed": info}

    if family:
        first = task_routing.family_plugin()
    else:
        wanted = task_routing.effective_place(current_user, db)
        first = plugin_registry.get(wanted) if wanted else None
    fb = task_routing.fallback_plugin()
    chain = [p for p in (first, fb) if p is not None]
    chain = [p for i, p in enumerate(chain) if p.id not in {q.id for q in chain[:i]}]
    if not chain:
        raise HTTPException(status_code=409, detail="Kein Aufgabenort verfügbar")
    last: HTTPException | None = None
    for plugin in chain:
        connector = plugin.task_connector(current_user.id, db)
        if connector is None:
            continue
        # Options depend on where the task finally lands (also after a fallback): Habitica gets its native to-do
        # options (difficulty via native.priority), every other provider only the plain priority.
        if not family and hasattr(connector, "action"):
            attempt = task.model_copy(update={"native": task_routing.habitica_native(task.native, own=True),
                                              "priority": None, "operation_id": task.operation_id or uuid.uuid4()})
        else:
            attempt = task.model_copy(update={"native": None, "operation_id": None})
        try:
            result = await _create_task_in(attempt, plugin.id, connector.account_ref, current_user, db)
        except HTTPException as exc:
            if exc.status_code not in (409, 422, 500, 503) or plugin is chain[-1]:
                raise
            last = exc
            continue
        return {**result, "placed": {"provider": plugin.id, "fallback": plugin is not first, "recipient": None}}
    raise last or HTTPException(status_code=409, detail="Kein Aufgabenort verfügbar")


async def _create_task_in(task: TaskCreateRequest, provider: str, account: str | None, current_user: User, db: Session):
    """Erstellt eine neue Aufgabe im ausdrücklich gewählten Anbieter (Legacy-Pfad und Ziel des Routings)."""
    _validate_people(task, current_user, db)

    connector = plugin_registry.task_connector(provider, current_user.id, db, account)

    if task.rotation:
        if not connector.is_configured:
            raise HTTPException(status_code=409, detail={"error": "no_caldav_account"})
        if provider == "nextcloud" and not db.query(TaskList).filter(
                TaskList.user_id == current_user.id, TaskList.kind == "family").first():
            raise HTTPException(status_code=409, detail="Bitte zuerst eine Nextcloud-Familienliste zuordnen")

    try:
        result = await connector.create_task(
            **({"native": task.native, "operation_id": str(task.operation_id)} if task.native is not None else {}),
            title=task.title,
            notes=task.notes,
            due=task.due,
            priority=task.priority,
            assignee_id=task.rotation[0] if task.rotation else task.assignee_id,
            list_kind=task.list,
            **({"recurrence": task.recurrence, "rotation": task.rotation,
                "habitica": False} if task.rotation else {}),
        )

        if not result:
            raise HTTPException(
                status_code=503 if task.rotation else status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create task",
            )

        # Push-Benachrichtigung bei Zuweisung an anderen Nutzer (resolved assignee: rotation[0] or assignee_id)
        await _notify_assigned(task, current_user, task.rotation[0] if task.rotation else task.assignee_id,
                               result.get("uid"))

        return context_task(result, provider, connector)

    except HTTPException:
        raise
    except ValueError as exc:
        # no_write_access:ListName
        exc_str = str(exc)
        if "no_write_access" in exc_str:
            list_name = exc_str.split(":", 1)[-1] if ":" in exc_str else "unknown"
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "no_write_access", "list": list_name},
            )
        raise
    except Exception as exc:
        logger.exception("Aufgabe anlegen fehlgeschlagen")  # Details nur ins Log, nicht an den Client
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Aufgabe konnte nicht angelegt werden",
        ) from exc



class TaskPlaceRequest(BaseModel):
    place: str | None = Field(None, max_length=32)  # task provider id; null = derive from connected accounts


@router.get("/me/place")
def get_task_place(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Where tasks that others give me land: ``place`` (effective), ``explicit`` (my choice), ``auto`` (derived)."""
    from app.services import task_routing

    return task_routing.place_info(current_user, db)


def _place_id(user: User, db: Session) -> str:
    from app.services import task_routing

    fb = task_routing.fallback_plugin()
    return task_routing.effective_place(user, db) or (fb.id if fb else "")


@router.get("/place/family")
def get_family_place(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Place type of the family list (where family tasks land), nothing else."""
    from app.services import task_routing

    plugin = task_routing.family_plugin() or task_routing.fallback_plugin()
    return {"place": plugin.id if plugin else ""}


@router.get("/place/{user_id}")
def get_place_of(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Only the place type where tasks for this family member land, so the creator's sheet can show matching
    fields. No accounts, lists or other data."""
    user = db.query(User).filter(User.id == user_id, User.is_active == True,  # noqa: E712
                                 User.role != "guest").first()
    if user is None:
        raise HTTPException(404, "Person nicht gefunden")
    return {"place": _place_id(user, db)}


@router.put("/me/place")
def set_task_place(data: TaskPlaceRequest, current_user: User = Depends(require_min_role(ROLE_CHILD)),
                   db: Session = Depends(get_db)):
    from app.services import task_routing

    options = task_routing.place_options(current_user.id, db)
    if data.place is not None and not any(o["id"] == data.place and o["available"] for o in options):
        raise HTTPException(422, "Dieser Aufgabenort ist nicht verfügbar. Bitte zuerst das Konto verbinden.")
    current_user.task_place = data.place
    db.commit()
    db.refresh(current_user)
    return task_routing.place_info(current_user, db)


class SelectionRequest(BaseModel):
    selected: bool


class NativeActionRequest(BaseModel):
    action: str
    operation_id: CanonicalUUID
    fields: dict = Field(default_factory=dict)
    item_id: str | None = None


@router.put("/{uid}/selection")
async def select_task(uid: str, data: SelectionRequest, provider: str, account: str,
                      current_user: User = Depends(require_min_role(ROLE_CHILD)), db: Session = Depends(get_db)):
    connector = plugin_registry.task_connector(provider, current_user.id, db, account)
    if not hasattr(connector, "select_task"):
        raise HTTPException(422, "Dieser Anbieter verwendet Listenauswahl")
    return await connector.select_task(uid, data.selected)


@router.post("/{uid}/actions")
async def native_action(uid: str, data: NativeActionRequest, provider: str, account: str,
                        current_user: User = Depends(require_min_role(ROLE_CHILD)), db: Session = Depends(get_db)):
    connector = plugin_registry.task_connector(provider, current_user.id, db, account)
    if not hasattr(connector, "action"):
        raise HTTPException(422, "Keine native Aktion für diesen Anbieter")
    return await connector.action(uid, data.action, str(data.operation_id), fields=data.fields, item_id=data.item_id)


@router.patch("/{uid}")
async def update_task(
    uid: str,
    task: TaskUpdateRequest,
    provider: str = "nextcloud",
    account: str | None = None,
    current_user: User = Depends(require_min_role(ROLE_PARTNER)),
    db: Session = Depends(get_db),
):
    """Aktualisiert eine Aufgabe."""

    connector = plugin_registry.task_connector(provider, current_user.id, db, account)

    updates = task.model_dump(exclude_unset=True)
    if "operation_id" in updates:
        updates["operation_id"] = str(task.operation_id)
    if task.title is not None:
        updates["title"] = task.title
    if task.notes is not None:
        updates["notes"] = task.notes
    if task.due is not None:
        updates["due"] = task.due
    if task.priority is not None:
        updates["priority"] = task.priority

    try:
        result = await connector.update_task(uid, **updates)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    return context_task(result, provider, connector)


@router.post("/{uid}/complete")
async def complete_task(
    uid: str,
    provider: str = "nextcloud",
    account: str | None = None,
    operation_id: CanonicalUUID | None = None,
    current_user: User = Depends(require_min_role(ROLE_CHILD)),
    db: Session = Depends(get_db),
):
    """Markiert Aufgabe als erledigt."""

    connector = plugin_registry.task_connector(provider, current_user.id, db, account)
    from app.connectors.nextcloud_tasks_connector import HouseholdUnavailable
    try:
        result = await connector.complete_task(uid, **({"operation_id": str(operation_id)} if operation_id else {}))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except HouseholdUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    if isinstance(result, dict):
        result.pop("_score", None)  # Legacy-Hinweis ist keine Autorisierung für ein anderes Plugin.

    return context_task(result, provider, connector)


@router.delete("/{uid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    uid: str,
    provider: str = "nextcloud",
    account: str | None = None,
    operation_id: CanonicalUUID | None = None,
    current_user: User = Depends(require_min_role(ROLE_PARTNER)),
    db: Session = Depends(get_db),
):
    """Löscht eine Aufgabe."""
    from app.connectors.nextcloud_tasks_connector import HouseholdUnavailable

    connector = plugin_registry.task_connector(provider, current_user.id, db, account)
    try:
        success = await connector.delete_task(uid, **({"operation_id": str(operation_id)} if operation_id else {}))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except HouseholdUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )


@router.get("/me/caldav")
async def get_caldav_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Gibt CalDAV-Account des Nutzers zurück (ohne Passwort)."""
    account = (
        db.query(CalDAVAccount)
        .filter(CalDAVAccount.user_id == current_user.id)
        .first()
    )

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No CalDAV account configured",
        )

    return CalDAVAccountResponse(
        url=account.url,
        username=account.username,
        has_password=bool(account.password_enc),
    )


@router.put("/me/caldav")
async def set_caldav_account(
    data: CalDAVAccountRequest,
    current_user: User = Depends(require_min_role(ROLE_CHILD)),
    db: Session = Depends(get_db),
):
    """Setzt oder aktualisiert CalDAV-Account des Nutzers."""
    account = (
        db.query(CalDAVAccount)
        .filter(CalDAVAccount.user_id == current_user.id)
        .first()
    )

    if account:
        # Update
        account.url = data.url
        account.username = data.username
        account.password_enc = encrypt(data.password)
    else:
        # Neu
        account = CalDAVAccount(
            user_id=current_user.id,
            url=data.url,
            username=data.username,
            password_enc=encrypt(data.password),
        )
        db.add(account)

    db.commit()
    db.refresh(account)

    return CalDAVAccountResponse(
        url=account.url,
        username=account.username,
        has_password=True,
    )


@router.get("/me/task-lists")
async def get_task_lists_config(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Gibt Task-Listen-Konfiguration des Nutzers zurück."""
    lists = (
        db.query(TaskList)
        .filter(TaskList.user_id == current_user.id)
        .all()
    )

    return [
        {
            "caldav_url": lst.caldav_url,
            "display_name": lst.display_name,
            "kind": lst.kind,
            "owner_user_id": lst.owner_user_id,
        }
        for lst in lists
    ]


@router.put("/me/task-lists")
async def set_task_lists_config(
    lists: List[TaskListConfigRequest],
    current_user: User = Depends(require_min_role(ROLE_CHILD)),
    db: Session = Depends(get_db),
):
    """Setzt Task-Listen-Konfiguration des Nutzers."""
    # Alte Konfiguration löschen
    db.query(TaskList).filter(TaskList.user_id == current_user.id).delete()

    # Neue Konfiguration speichern
    for lst in lists:
        task_list = TaskList(
            user_id=current_user.id,
            caldav_url=lst.caldav_url,
            display_name=lst.caldav_url.split("/")[-1],  # Fallback
            kind=lst.kind,
            owner_user_id=lst.owner_user_id,
        )
        db.add(task_list)

    db.commit()

    return {"status": "ok"}
