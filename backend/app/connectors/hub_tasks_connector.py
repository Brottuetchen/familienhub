"""Tasks stored in the hub itself, the built-in task source (plugin ``hub_tasks``).

Same contract as the Nextcloud connector, so the router, Today and the app treat both alike:
- personal tasks belong to the assignee (or the creator) and are visible only to owner and creator
- family tasks are visible to everyone; household tasks rotate to the next person on completion
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import or_

from app.core.database import SessionLocal
from app.models.hub import HubTask
from app.models.user import User
from app.services.recurrence import advance

FAMILY_LIST = {"name": "Familie", "kind": "family"}
PERSONAL_LIST = {"name": "Persönlich", "kind": "personal"}


def _next_due(due: Optional[str], recurrence: str) -> Optional[str]:
    if not due:
        return None
    date_only = len(due) == 10
    current = datetime.fromisoformat(due.replace("Z", "+00:00"))
    nxt = advance(current, recurrence)
    if nxt is None:
        return None
    return nxt.date().isoformat() if date_only else nxt.isoformat()


class HubTasksConnector:
    name = "hub_tasks"

    def __init__(self, user_id: int):
        self.user_id = user_id

    @property
    def account_ref(self) -> str:
        return f"{self.user_id}:hub"

    @property
    def is_configured(self) -> bool:
        return True

    # --- helpers ---

    def _owner(self, t: HubTask) -> Optional[int]:
        return t.assignee_id or t.created_by

    def _visible(self, t: HubTask) -> bool:
        return t.family or self.user_id in (t.created_by, self._owner(t))

    def _to_dict(self, t: HubTask) -> Dict[str, Any]:
        return {
            "uid": t.uid, "title": t.title, "notes": t.notes or "", "due": t.due, "priority": t.priority,
            "done": bool(t.done), "list": dict(FAMILY_LIST if t.family else PERSONAL_LIST),
            "created_by": t.created_by, "assignee": t.assignee_id,
            "recurrence": t.recurrence or "none", "rotation": list(t.rotation or []), "habitica": False, "etag": None,
        }

    def _get(self, db, uid: str) -> Optional[HubTask]:
        t = db.get(HubTask, uid)
        return t if t is not None and self._visible(t) else None

    # --- contract ---

    async def get_lists(self) -> Dict[str, Any]:
        return {"status": "ok", "error": None, "lists": []}

    async def get_tasks(self, view: str = "all", include_done: bool = False) -> Dict[str, Any]:
        me = self.user_id
        with SessionLocal() as db:
            q = db.query(HubTask)
            if not include_done:
                q = q.filter(HubTask.done == False)  # noqa: E712
            q = q.filter(or_(HubTask.family == True, HubTask.created_by == me, HubTask.assignee_id == me))  # noqa: E712
            items = []
            for t in q.order_by(HubTask.created_at).all():
                owner, mine = self._owner(t), t.created_by in (me, None)
                personal = not t.family
                keep = {
                    "mine": personal and owner == me and mine,
                    "for_me": personal and owner == me and not mine,
                    "from_me": personal and t.created_by == me and owner != me,
                    "family": t.family,
                }.get(view, self._visible(t))
                if keep:
                    items.append(self._to_dict(t))
        return {"status": "ok", "error": None, "items": items}

    async def create_task(self, title: str, notes: Optional[str] = None, due: Optional[str] = None,
                          priority: Optional[int] = None, assignee_id: Optional[int] = None,
                          list_kind: Optional[str] = None, recurrence: str = "none",
                          rotation: Optional[List[int]] = None, habitica: bool = False, **_: Any) -> Dict[str, Any]:
        with SessionLocal() as db:
            t = HubTask(uid=str(uuid.uuid4()), title=title.strip()[:200], notes=notes or "", due=due, priority=priority,
                        family=list_kind == "family", created_by=self.user_id, assignee_id=assignee_id,
                        recurrence=recurrence or "none", rotation=list(rotation or []))
            db.add(t)
            db.commit()
            return self._to_dict(t)

    async def update_task(self, uid: str, **changes: Any) -> Optional[Dict[str, Any]]:
        with SessionLocal() as db:
            t = self._get(db, uid)
            if t is None:
                return None
            if t.rotation:
                self._check_household(db, t, manage=True)
            for key in ("title", "notes", "due", "priority"):
                if key in changes:
                    value = changes[key]
                    if key == "title" and (not value or not str(value).strip()):
                        raise ValueError("Titel fehlt")
                    setattr(t, key, value.strip()[:200] if key == "title" else value)
            db.commit()
            return self._to_dict(t)

    def _check_household(self, db, t: HubTask, manage: bool = False) -> None:
        user = db.get(User, self.user_id)
        if not user or user.role == "guest" or (
                user.role not in ("admin", "partner") and (manage or t.assignee_id != user.id)):
            raise PermissionError("Diese Haushaltsaufgabe darfst du nicht ändern")

    async def complete_task(self, uid: str, **_: Any) -> Optional[Dict[str, Any]]:
        with SessionLocal() as db:
            t = self._get(db, uid)
            if t is None:
                return None
            if t.rotation:
                self._check_household(db, t)
            if t.done:
                return self._to_dict(t)
            t.done, t.completed_at = True, datetime.utcnow()
            if t.rotation and t.recurrence != "none" and not t.successor_uid:
                self._create_successor(db, t)
            db.commit()
            return self._to_dict(t)

    def _create_successor(self, db, t: HubTask) -> None:
        rotation = list(t.rotation)
        active = {u.id for u in db.query(User).filter(User.is_active == True, User.role != "guest")}  # noqa: E712
        start = rotation.index(t.assignee_id) if t.assignee_id in rotation else -1
        assignee = next((rotation[(start + i) % len(rotation)] for i in range(1, len(rotation) + 1)
                         if rotation[(start + i) % len(rotation)] in active), None)
        due = _next_due(t.due, t.recurrence)
        if assignee is None or due is None:
            return  # nobody left or no due date: the series ends here
        successor = str(uuid5(NAMESPACE_URL, f"familienhub/hub/{t.uid}/next"))
        t.successor_uid = successor
        db.add(HubTask(uid=successor, title=t.title, notes=t.notes, due=due, priority=t.priority, family=True,
                       created_by=t.created_by, assignee_id=assignee, recurrence=t.recurrence, rotation=rotation))

    async def delete_task(self, uid: str, **_: Any) -> bool:
        with SessionLocal() as db:
            t = self._get(db, uid)
            if t is None:
                return False
            if t.rotation:
                self._check_household(db, t, manage=True)
            db.delete(t)
            db.commit()
            return True
