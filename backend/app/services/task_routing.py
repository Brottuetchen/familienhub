"""Tasks go where the recipient works (#38).

- Every person has a preferred task place: their explicit choice (``User.task_place``), else derived from the
  connected accounts: CalDAV (Nextcloud) account > Habitica account (writes released) > the hub itself.
- A task for another person is written with the *recipient's own* connector (their stored credentials),
  never with the creator's account. If the recipient has no usable account for the place, or the provider
  fails, the task lands in the hub instead.
- A small :class:`TaskAssignment` row links creator, recipient and remote object so the creator's
  "Von mir" view can list the task and show whether it is done. Nothing else of the recipient's lists is read
  for the creator.
- Family tasks and household rotation use the family list of the first source of the area that has one.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.task_assignment import TaskAssignment
from app.models.user import User
from app.plugins.registry import plugin_registry

logger = logging.getLogger("hermes.task_routing")

# Source names of the hub itself are never hard-coded: the fallback is the active tasks plugin flagged ``fallback``.


def _ordered_providers() -> list:
    """Active task sources, built-in order, the hub's own source last."""
    return sorted(plugin_registry.providers("tasks"), key=lambda p: p.fallback)


def fallback_plugin():
    return next((p for p in _ordered_providers() if p.fallback), None)


def _connector(plugin, user_id: int, db: Session):
    try:
        return plugin.task_connector(user_id, db)
    except Exception:  # noqa: BLE001 - an unavailable provider is simply "not available"
        logger.warning("Task connector %s not ready", plugin.id, exc_info=True)
        return None


def _can_receive(connector) -> bool:
    if connector is None or not connector.is_configured:
        return False
    return bool(getattr(connector, "accepts_assigned", True))


def place_options(user_id: int, db: Session) -> List[Dict[str, Any]]:
    """Task sources and whether this person can use them as the place for tasks that others give them."""
    out = []
    for plugin in _ordered_providers():
        connector = _connector(plugin, user_id, db)
        out.append({"id": plugin.id, "name": plugin.name, "available": plugin.fallback or _can_receive(connector)})
    return out


def derived_place(options: List[Dict[str, Any]]) -> Optional[str]:
    """Default place: first available source in order (CalDAV > Habitica > others > hub)."""
    return next((o["id"] for o in options if o["available"]), None)


def place_info(user: User, db: Session) -> Dict[str, Any]:
    options = place_options(user.id, db)
    auto = derived_place(options)
    explicit = user.task_place if any(o["id"] == user.task_place and o["available"] for o in options) else None
    return {"place": explicit or auto, "explicit": user.task_place, "auto": auto, "options": options}


def effective_place(user: User, db: Session) -> Optional[str]:
    return place_info(user, db)["place"]


# Options of a Habitica to-do that may be set when a task is created through the router (#58). Everything
# else is stripped: the checklist is only editable after creation (native contract), ``date`` is the
# task's ``due`` and reminders/alias belong to the account screen.
_NATIVE_OPTIONS_OWN = {"priority", "attribute", "tags", "collapseChecklist"}
_NATIVE_OPTIONS_OTHER = {"priority", "attribute"}  # tags are ids of the recipient's own account: unknown here


def habitica_native(native: Optional[Dict[str, Any]], *, own: bool) -> Dict[str, Any]:
    """Native options for a Habitica to-do created via ``provider=auto``; unknown or foreign options are dropped."""
    from app.connectors.habitica_connector import TYPES

    native = native if isinstance(native, dict) else {}
    kind = native.get("type", "todo") if own else "todo"
    if kind not in TYPES:
        kind = "todo"
    allowed = (_NATIVE_OPTIONS_OWN if own else _NATIVE_OPTIONS_OTHER) if kind == "todo" else set()
    return {"type": kind, **{k: v for k, v in native.items() if k in allowed}}


def family_plugin():
    """Source of the family list / household rotation: first active source that can hold one (hub last)."""
    return next((p for p in _ordered_providers() if p.family_tasks), None)


async def _create_in(plugin, recipient_id: int, creator: User, db: Session, *, notes: Optional[str],
                     native: Optional[Dict[str, Any]] = None, **fields) -> Optional[tuple]:
    connector = _connector(plugin, recipient_id, db)
    if not _can_receive(connector):
        return None
    extra: Dict[str, Any] = {}
    if hasattr(connector, "action"):  # native provider (Habitica): plain todo, guarded by an operation id;
        # it has no creator field, so the notes say who assigned it
        extra = {"native": habitica_native(native, own=False), "operation_id": str(uuid.uuid4())}
        notes = _with_creator(notes, creator)
    try:
        result = await connector.create_task(assignee_id=recipient_id, created_by=creator.id, notes=notes,
                                             **extra, **fields)
    except Exception:  # noqa: BLE001 - provider failure means: use the next place
        logger.warning("Task for user %s could not be created in %s", recipient_id, plugin.id, exc_info=True)
        return None
    return (result, connector) if result else None


async def create_for_recipient(creator: User, recipient: User, db: Session, *, title: str, notes: Optional[str],
                               due: Optional[str], priority: Optional[int],
                               native: Optional[Dict[str, Any]] = None):
    """Create the task in the recipient's place (fallback: hub). Returns (task dict, connector, assignment row)."""
    place = effective_place(recipient, db)
    fb = fallback_plugin()
    chain = [plugin_registry.get(place)] if place else []
    if fb is not None and fb.id != place:
        chain.append(fb)
    for plugin in chain:
        if plugin is None:
            continue
        created = await _create_in(plugin, recipient.id, creator, db, title=title, notes=notes, due=due,
                                   priority=priority, native=native)
        if created is None:
            continue
        result, connector = created
        row = TaskAssignment(creator_id=creator.id, assignee_id=recipient.id, provider=plugin.id,
                             account_ref=connector.account_ref, remote_uid=str(result["uid"]), title=title.strip()[:200],
                             due=due, fallback=bool(place and plugin.id != place), done=bool(result.get("done")),
                             synced_at=datetime.utcnow())
        db.add(row)
        db.commit()
        return result, connector, row, plugin
    return None


def _with_creator(notes: Optional[str], creator: User) -> str:
    """Providers without a creator field (Habitica) show who assigned the task in the notes."""
    line = f"Von {creator.effective_name}"
    return f"{notes}\n\n{line}" if notes else line


# --- "Von mir": assigned tasks and their status ---------------------------------------------------------


async def refresh_status(rows: List[TaskAssignment], db: Session) -> None:
    """Read open/done from each recipient's provider, through the recipient's own connector. Fails soft."""
    pending = [r for r in rows if not r.done]
    groups: Dict[tuple, List[TaskAssignment]] = {}
    for r in pending:
        groups.setdefault((r.assignee_id, r.provider), []).append(r)
    for (assignee_id, provider), group in groups.items():
        plugin = plugin_registry.get(provider)
        connector = _connector(plugin, assignee_id, db) if plugin and plugin_registry.serves("tasks", provider) else None
        if connector is None or not connector.is_configured:
            for r in group:
                r.sync_ok = False
            continue
        try:
            if hasattr(connector, "get_task"):
                await _refresh_native(connector, group, db)
            else:
                await _refresh_listed(connector, group, db)
        except Exception:  # noqa: BLE001
            logger.warning("Assigned task status not readable (%s)", provider, exc_info=True)
            for r in group:
                r.sync_ok = False
    db.commit()


async def _refresh_listed(connector, group: List[TaskAssignment], db: Session) -> None:
    result = await connector.get_tasks(view="all", include_done=True)
    if result.get("status") != "ok":
        for r in group:
            r.sync_ok = False
        return
    by_uid = {t.get("uid"): t for t in result.get("items", []) if isinstance(t, dict)}
    for r in group:
        task = by_uid.get(r.remote_uid)
        if task is None:
            db.delete(r)  # removed by the recipient
            continue
        r.done, r.sync_ok, r.synced_at = bool(task.get("done")), True, datetime.utcnow()


async def _refresh_native(connector, group: List[TaskAssignment], db: Session) -> None:
    from fastapi import HTTPException

    for r in group:
        try:
            remote = await connector.get_task(r.remote_uid)
        except HTTPException as exc:
            if exc.status_code == 404:
                db.delete(r)
            else:
                r.sync_ok = False
            continue
        r.done, r.sync_ok, r.synced_at = bool(remote.get("completed")), True, datetime.utcnow()


def to_item(row: TaskAssignment) -> Dict[str, Any]:
    """Item for the creator's list: read-only, only what the creator wrote plus the status."""
    return {"uid": row.remote_uid, "title": row.title, "notes": "", "due": row.due, "priority": None,
            "done": bool(row.done), "list": {"name": row.provider, "kind": "personal"},
            "created_by": row.creator_id, "assignee": row.assignee_id, "recurrence": "none", "rotation": [],
            "habitica": False, "etag": None, "provider": "assigned", "account": "", "read_only": True,
            "via": row.provider, "stale": not row.sync_ok, "fallback": bool(row.fallback)}


async def assigned_items(creator_id: int, db: Session, include_done: bool = False,
                         skip: Optional[set] = None) -> List[Dict[str, Any]]:
    """Tasks the creator gave to others, living outside the hub (hub tasks already show up natively).

    ``skip`` holds (provider, uid) pairs the normal provider read already returned.
    """
    rows = (db.query(TaskAssignment).filter(TaskAssignment.creator_id == creator_id)
            .order_by(TaskAssignment.created_at).all())
    rows = [r for r in rows if not _is_native_hub(r)]
    await refresh_status(rows, db)
    out = []
    for r in db.query(TaskAssignment).filter(TaskAssignment.creator_id == creator_id).order_by(TaskAssignment.created_at):
        if _is_native_hub(r) or (r.provider, r.remote_uid) in (skip or set()):
            continue
        if r.done and not include_done:
            continue
        out.append(to_item(r))
    return out


def _is_native_hub(row: TaskAssignment) -> bool:
    plugin = plugin_registry.get(row.provider)
    return bool(plugin and plugin.fallback)
