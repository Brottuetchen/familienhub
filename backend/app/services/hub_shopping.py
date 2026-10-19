"""Shopping list stored in the hub (plugin ``hub_shopping``), same shape as the Home Assistant list."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.database import SessionLocal
from app.models.hub import HubShoppingItem


def _item(i: HubShoppingItem) -> Dict[str, Any]:
    return {"uid": str(i.id), "summary": i.summary, "status": "completed" if i.done else "needs_action"}


def _id(uid: str) -> Optional[int]:
    return int(uid) if uid.isdecimal() else None


class HubShopping:
    async def groups(self) -> Dict[str, Any]:
        with SessionLocal() as db:
            items = db.query(HubShoppingItem).order_by(HubShoppingItem.done, HubShoppingItem.created_at).all()
            out = [_item(i) for i in items]
        from app.services import shopping_recipes

        return {"status": "ok", "error": None,
                "groups": [{"key": "manual", "entity": "hub", "items": shopping_recipes.attach("hub", out)}]}

    async def open_items(self) -> List[Dict[str, Any]]:
        with SessionLocal() as db:
            rows = db.query(HubShoppingItem).filter(HubShoppingItem.done == False).order_by(  # noqa: E712
                HubShoppingItem.created_at).all()
            return [{"uid": str(i.id), "summary": i.summary} for i in rows]

    async def rename(self, uid: str, summary: str) -> bool:
        with SessionLocal() as db:
            item = db.get(HubShoppingItem, _id(uid)) if _id(uid) is not None else None
            if item is None:
                return False
            item.summary = summary.strip()[:200]
            db.commit()
        return True

    async def add(self, summary: str, user_id: Optional[int]) -> bool:
        summary = summary.strip()[:200]
        if not summary:
            return False
        with SessionLocal() as db:
            db.add(HubShoppingItem(summary=summary, created_by=user_id))
            db.commit()
        return True

    async def set_done(self, uid: str, done: bool) -> bool:
        with SessionLocal() as db:
            item = db.get(HubShoppingItem, _id(uid)) if _id(uid) is not None else None
            if item is None:
                return False
            item.done, item.completed_at = done, (datetime.utcnow() if done else None)
            db.commit()
        return True

    async def delete(self, uid: str) -> bool:
        with SessionLocal() as db:
            item = db.get(HubShoppingItem, _id(uid)) if _id(uid) is not None else None
            if item is None:
                return False
            db.delete(item)
            db.commit()
        return True

    async def recent(self) -> List[str]:
        """Recently ticked-off items as suggestions, newest first, without duplicates."""
        with SessionLocal() as db:
            done = (db.query(HubShoppingItem).filter(HubShoppingItem.done == True)  # noqa: E712
                    .order_by(HubShoppingItem.completed_at.desc()).limit(200).all())
            seen, out = set(), []
            for i in done:
                if i.summary.lower() not in seen:
                    seen.add(i.summary.lower())
                    out.append(i.summary)
            return out[:30]

    async def open_count(self) -> int:
        with SessionLocal() as db:
            return db.query(HubShoppingItem).filter(HubShoppingItem.done == False).count()  # noqa: E712
