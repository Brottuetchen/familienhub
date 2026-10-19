"""Administration → Updates: is a newer Familienhub release available? (admin only)"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_min_role
from app.models.user import ROLE_ADMIN, User
from app.services import config_store, update_check

router = APIRouter(prefix="/api/admin/update", tags=["admin"])
admin_only = require_min_role(ROLE_ADMIN)


@router.get("")
async def get_update(_: User = Depends(admin_only)):
    """Newest release newer than the running version, from a cache that is refreshed a few times a day."""
    return await update_check.status()


class UpdateSettings(BaseModel):
    enabled: bool
    repo: str = ""


@router.put("/settings")
async def put_update_settings(data: UpdateSettings, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    repo = data.repo.strip() or "Brottuetchen/familienhub"
    if not update_check.REPO_RE.match(repo):
        raise HTTPException(status_code=422, detail="Use the form owner/name for the repository")
    config_store.save_overrides(db, {"UPDATE_CHECK": "true" if data.enabled else "false", "UPDATE_CHECK_REPO": repo})
    update_check.reset()
    return await update_check.status()
