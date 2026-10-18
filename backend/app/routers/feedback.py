"""Rückmeldungen und App-Fehler aus der App (Beta).

- ``POST /api/feedback``: Text an die Admins (gespeichert, Mitteilung an Admins).
- ``GET /api/admin/feedback`` / ``POST /api/admin/feedback/{id}/done``: Liste und erledigt markieren.
- ``POST /api/client-errors``: Fehler der App ins Protokoll der Verwaltung (geschwärzt, begrenzt pro Person).
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Deque, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_min_role
from app.models.feedback import Feedback
from app.models.user import ROLE_ADMIN, User
from app.services.notify import notify

router = APIRouter(tags=["feedback"])
client_log = logging.getLogger("familienhub.app")

PLATFORMS = ("android", "ios", "web", "other")


class FeedbackIn(BaseModel):
    text: str = Field(min_length=3, max_length=4000)
    area: str | None = Field(default=None, max_length=40)
    app_version: str | None = Field(default=None, max_length=40)
    platform: str | None = Field(default=None, max_length=20)


@router.post("/api/feedback", status_code=201)
async def send_feedback(data: FeedbackIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    platform = data.platform if data.platform in PLATFORMS else "other"
    fb = Feedback(user_id=user.id, text=data.text.strip(), area=(data.area or "").strip() or None,
                  app_version=(data.app_version or "").strip() or None, platform=platform)
    db.add(fb)
    db.commit()
    db.refresh(fb)
    admins = db.query(User).filter(User.is_admin == True, User.is_active == True).all()  # noqa: E712
    for a in admins:
        if a.id != user.id:
            await notify(a.id, f"💬 Feedback von {user.effective_name}", data.text.strip()[:200],
                         data={"route": "/admin/feedback"}, category="system", source="app")
    return {"id": fb.id}


@router.get("/api/admin/feedback")
async def list_feedback(db: Session = Depends(get_db), _: User = Depends(require_min_role(ROLE_ADMIN))):
    rows = db.query(Feedback, User).outerjoin(User, User.id == Feedback.user_id).order_by(Feedback.created_at.desc()).limit(200).all()
    return {"items": [{
        "id": f.id, "text": f.text, "area": f.area, "app_version": f.app_version, "platform": f.platform,
        "created_at": f.created_at.isoformat(), "done": f.done_at is not None,
        "from": u.effective_name if u else "Gelöschte Person",
    } for f, u in rows]}


@router.post("/api/admin/feedback/{feedback_id}/done")
async def feedback_done(feedback_id: int, db: Session = Depends(get_db), _: User = Depends(require_min_role(ROLE_ADMIN))):
    fb = db.get(Feedback, feedback_id)
    if not fb:
        raise HTTPException(404, "Nicht gefunden")
    fb.done_at = fb.done_at or datetime.utcnow()
    db.commit()
    return {"done": True}


class ClientError(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    stack: str | None = Field(default=None, max_length=4000)
    app_version: str | None = Field(default=None, max_length=40)
    platform: str | None = Field(default=None, max_length=20)


MAX_PER_HOUR = 30
_recent: Dict[int, Deque[float]] = defaultdict(deque)


@router.post("/api/client-errors", status_code=202)
async def client_error(data: ClientError, user: User = Depends(get_current_user)):
    """Fehler der App: landen geschwärzt im Protokoll der Verwaltung. Höchstens 30 pro Person und Stunde."""
    now = time.monotonic()
    seen = _recent[user.id]
    while seen and now - seen[0] > 3600:
        seen.popleft()
    if len(seen) >= MAX_PER_HOUR:
        return {"accepted": False}
    seen.append(now)
    first_frame = next((line.strip() for line in (data.stack or "").splitlines() if "package:familienhub" in line), "")
    platform = data.platform if data.platform in PLATFORMS else "other"
    client_log.warning("App-Fehler (%s, %s, %s): %s %s", platform, data.app_version or "?", user.username,
                       data.message.strip()[:300], first_frame[:200])
    return {"accepted": True}
