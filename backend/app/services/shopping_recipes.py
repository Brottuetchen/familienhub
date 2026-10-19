"""Recipe references of shopping entries (#69): which recipes an entry is on the list for.

Storage is a small table keyed by list scope and normalised entry text (see ``ShoppingItemRecipes``). Everything
here fails softly: a database problem means "no recipes known", never a broken shopping list.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List

from app.core.database import SessionLocal
from app.models.hub import ShoppingItemRecipes

logger = logging.getLogger("hermes.shopping")


def key(summary: str) -> str:
    return " ".join((summary or "").lower().split())[:220]


def lookup(scope: str, summaries: Iterable[str], prune: bool = True) -> Dict[str, List[str]]:
    """``{normalised summary: [recipe names]}`` for the given open entries; rows of other entries are dropped."""
    wanted = {key(s) for s in summaries}
    try:
        with SessionLocal() as db:
            rows = db.query(ShoppingItemRecipes).filter(ShoppingItemRecipes.scope == scope).all()
            found = {r.item_key: list(r.recipes or []) for r in rows if r.item_key in wanted}
            stale = [r for r in rows if r.item_key not in wanted]
            if prune and stale:
                for r in stale:
                    db.delete(r)
                db.commit()
            return found
    except Exception as exc:  # noqa: BLE001 - recipe hints are optional
        logger.warning("Recipe references not read: %s", type(exc).__name__)
        return {}


def store(scope: str, summary: str, recipes: List[str], replace_key: str = "") -> None:
    """Remember the recipes of an entry; ``replace_key`` (old text) is removed when the entry was renamed by a merge."""
    try:
        with SessionLocal() as db:
            if replace_key and key(replace_key) != key(summary):
                db.query(ShoppingItemRecipes).filter_by(scope=scope, item_key=key(replace_key)).delete()
            row = db.query(ShoppingItemRecipes).filter_by(scope=scope, item_key=key(summary)).first()
            if row is None:
                row = ShoppingItemRecipes(scope=scope, item_key=key(summary), recipes=[])
                db.add(row)
            merged = list(row.recipes or [])
            merged += [r for r in recipes if r not in merged]
            row.recipes = merged
            db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Recipe references not saved: %s", type(exc).__name__)


def attach(scope: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add ``recipes`` to each item dict (empty list when unknown). Done items keep theirs; only unknown rows are pruned."""
    open_ = [i.get("summary") or "" for i in items if i.get("status") != "completed"]  # done entries lose their rows
    refs = lookup(scope, open_)
    for item in items:
        item.setdefault("recipes", refs.get(key(item.get("summary") or ""), []))
    return items
