"""Layout of the "Today" screen: ordered cards with visibility and size (bento).

Resolution order for a person: own layout, then the family default set by an admin, then the built-in
default, which matches the arrangement the app had before the layout became customisable.
"""

from __future__ import annotations

import json
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.config import ConfigOverride
from app.models.today_layout import TodayLayout

SIZES = ("full", "half")
DEFAULT_KEY = "TODAY_LAYOUT_DEFAULT"

# Original order; shopping and events sit side by side
BUILTIN: List[dict] = [
    {"id": "tasks", "visible": True, "size": "full"},
    {"id": "shopping", "visible": True, "size": "half"},
    {"id": "events", "visible": True, "size": "half"},
    {"id": "meals", "visible": True, "size": "full"},
    {"id": "reminders", "visible": True, "size": "full"},
    {"id": "house", "visible": True, "size": "full"},
    {"id": "birthdays", "visible": True, "size": "full"},
    {"id": "timetable", "visible": True, "size": "full"},
]
KNOWN = {c["id"] for c in BUILTIN}


def normalize(cards: list) -> List[dict]:
    """Drops unknown ids and duplicates, appends missing cards with their built-in defaults."""
    out, seen = [], set()
    for c in cards or []:
        if not isinstance(c, dict) or c.get("id") not in KNOWN or c["id"] in seen:
            continue
        seen.add(c["id"])
        out.append({"id": c["id"], "visible": bool(c.get("visible", True)),
                    "size": c.get("size") if c.get("size") in SIZES else "full"})
    out.extend(dict(c) for c in BUILTIN if c["id"] not in seen)
    return out


def _load(raw: Optional[str]) -> Optional[List[dict]]:
    try:
        data = json.loads(raw) if raw else None
    except ValueError:
        return None
    return normalize(data) if isinstance(data, list) else None


def family_default(db: Session) -> Optional[List[dict]]:
    row = db.get(ConfigOverride, DEFAULT_KEY)
    return _load(row.value) if row else None


def effective(db: Session, user_id: int) -> dict:
    own = db.get(TodayLayout, user_id)
    cards = _load(own.layout) if own else None
    if cards is not None:
        return {"cards": cards, "source": "user"}
    cards = family_default(db)
    if cards is not None:
        return {"cards": cards, "source": "family"}
    return {"cards": normalize([]), "source": "builtin"}


def save_own(db: Session, user_id: int, cards: List[dict]) -> None:
    row = db.get(TodayLayout, user_id) or TodayLayout(user_id=user_id)
    row.layout = json.dumps(cards)
    db.add(row)
    db.commit()


def reset_own(db: Session, user_id: int) -> None:
    row = db.get(TodayLayout, user_id)
    if row is not None:
        db.delete(row)
        db.commit()


def save_family_default(db: Session, cards: List[dict]) -> None:
    row = db.get(ConfigOverride, DEFAULT_KEY) or ConfigOverride(key=DEFAULT_KEY)
    row.value, row.secret = json.dumps(cards), False
    db.add(row)
    db.commit()


def reset_family_default(db: Session) -> None:
    row = db.get(ConfigOverride, DEFAULT_KEY)
    if row is not None:
        db.delete(row)
        db.commit()
