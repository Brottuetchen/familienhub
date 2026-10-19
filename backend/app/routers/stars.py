"""Kids mode: stars for tasks, rewards and reward requests.

Parents (partner/admin) hand out stars on tasks, define rewards, decide on requests and confirmations.
Children read their own balance, ask for rewards and cancel their own open requests.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_min_role
from app.models.stars import StarLedger, StarRequest, StarReward
from app.models.user import ROLE_CHILD, ROLE_PARTNER, User
from app.services import stars as svc

router = APIRouter(prefix="/api/stars", tags=["stars"])

_parent = require_min_role(ROLE_PARTNER)
_member = require_min_role(ROLE_CHILD)  # everyone but guests


class SettingsIn(BaseModel):
    confirm_tasks: bool


class RewardIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    price: int = Field(ge=1, le=svc.MAX_PRICE)


class RewardPatch(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=120)
    price: Optional[int] = Field(None, ge=1, le=svc.MAX_PRICE)
    active: Optional[bool] = None


class RequestIn(BaseModel):
    reward_id: int


class AdjustIn(BaseModel):
    user_id: int
    delta: int = Field(ge=-svc.MAX_ADJUST, le=svc.MAX_ADJUST)
    title: str = Field("", max_length=200)


class TaskStarsIn(BaseModel):
    stars: int = Field(ge=0, le=svc.MAX_TASK_STARS)


def _names(db: Session, ids) -> dict:
    return {u.id: svc.display(u) for u in db.query(User).filter(User.id.in_(set(ids))).all()} if ids else {}


async def _notify(user_id: int, title: str, body: str, route: str) -> None:
    from app.services.notify import notify

    try:
        await notify(user_id=user_id, title=title, body=body, data={"route": route}, category="stars")
    except Exception:  # noqa: BLE001 - a failed push never blocks the stars flow
        pass


async def notify_parents(db: Session, title: str, body: str, skip: int | None = None) -> None:
    for parent in svc.parents(db):
        if parent.id != skip:
            await _notify(parent.id, title, body, "/stars")


# --- own view ---


@router.get("/me")
def my_stars(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Balance, next reward and (for parents) open decisions. ``enabled`` false hides the Today card."""
    return svc.summary(db, user)


@router.get("/settings")
def get_settings(_: User = Depends(_member), db: Session = Depends(get_db)):
    return {"confirm_tasks": svc.confirm_required(db)}


@router.put("/settings")
def put_settings(body: SettingsIn, _: User = Depends(_parent), db: Session = Depends(get_db)):
    svc.set_confirm_required(db, body.confirm_tasks)
    return {"confirm_tasks": body.confirm_tasks}


# --- people (parents) ---


@router.get("/people")
def people(_: User = Depends(_parent), db: Session = Depends(get_db)):
    """Everyone with stars use: children always, others once they have an account."""
    from app.models.stars import StarAccount

    accounts = {a.user_id: a for a in db.query(StarAccount).all()}
    out = []
    for u in db.query(User).filter(User.is_active == True, User.role != "guest").order_by(User.id):  # noqa: E712
        if u.role == ROLE_CHILD or u.id in accounts:
            a = accounts.get(u.id)
            balance, reserved = (a.balance, a.reserved) if a else (0, 0)
            out.append({"id": u.id, "name": svc.display(u), "role": u.role, "balance": balance,
                        "reserved": reserved, "available": balance - reserved})
    return {"items": out}


# --- stars on tasks ---


@router.put("/tasks/{provider}/{uid}")
def put_task_stars(provider: str, uid: str, body: TaskStarsIn, user: User = Depends(_parent),
                   db: Session = Depends(get_db)):
    """Sets (0 removes) the stars of a task from any source. Only parents may."""
    if provider == "habitica":
        raise HTTPException(422, "Habitica vergibt eigene Belohnungen")
    return {"provider": provider, "uid": uid, "stars": svc.set_task_stars(db, provider[:32], uid[:255], body.stars, user)}


# --- rewards ---


@router.get("/rewards")
def list_rewards(user: User = Depends(_member), db: Session = Depends(get_db)):
    q = db.query(StarReward).order_by(StarReward.price, StarReward.id)
    if not svc.is_parent(user):
        q = q.filter(StarReward.active == True)  # noqa: E712
    return {"items": [svc.reward_dict(r) for r in q.all()]}


@router.post("/rewards", status_code=201)
def add_reward(body: RewardIn, user: User = Depends(_parent), db: Session = Depends(get_db)):
    if not body.title.strip():
        raise HTTPException(422, "Titel fehlt")
    return svc.reward_dict(svc.create_reward(db, body.title, body.price, user))


@router.patch("/rewards/{reward_id}")
def edit_reward(reward_id: int, body: RewardPatch, _: User = Depends(_parent), db: Session = Depends(get_db)):
    reward = db.get(StarReward, reward_id)
    if reward is None:
        raise HTTPException(404, "Belohnung nicht gefunden")
    if body.title is not None:
        if not body.title.strip():
            raise HTTPException(422, "Titel fehlt")
        reward.title = body.title.strip()
    if body.price is not None:
        reward.price = body.price
    if body.active is not None:
        reward.active = body.active
    db.commit()
    return svc.reward_dict(reward)


@router.delete("/rewards/{reward_id}", status_code=204)
def remove_reward(reward_id: int, _: User = Depends(_parent), db: Session = Depends(get_db)):
    """Switches the reward off. Old requests keep their copy of title and price."""
    reward = db.get(StarReward, reward_id)
    if reward is None:
        raise HTTPException(404, "Belohnung nicht gefunden")
    reward.active = False
    db.commit()


# --- reward requests ---


@router.post("/requests", status_code=201)
async def request_reward(body: RequestIn, user: User = Depends(_member), db: Session = Depends(get_db)):
    req = svc.request_reward(db, user, body.reward_id)
    await notify_parents(db, "Belohnung gewünscht", f"{svc.display(user)}: {req.title} ({req.price} ⭐)", skip=user.id)
    return svc.request_dict(req, svc.display(user))


@router.get("/requests")
def list_requests(status: Optional[str] = None, user_id: Optional[int] = None, user: User = Depends(_member),
                  db: Session = Depends(get_db)):
    """Parents see everyone's requests (filter by ``user_id``), everyone else only their own."""
    q = db.query(StarRequest)
    if svc.is_parent(user):
        if user_id is not None:
            q = q.filter(StarRequest.user_id == user_id)
    else:
        q = q.filter(StarRequest.user_id == user.id)
    if status:
        q = q.filter(StarRequest.status == status)
    rows = q.order_by(StarRequest.id.desc()).limit(200).all()
    names = _names(db, {r.user_id for r in rows})
    return {"items": [svc.request_dict(r, names.get(r.user_id, "")) for r in rows]}


@router.post("/requests/{req_id}/approve")
async def approve_request(req_id: int, user: User = Depends(_parent), db: Session = Depends(get_db)):
    req = svc.decide_request(db, req_id, True, user)
    await _notify(req.user_id, "Belohnung bewilligt", f"{req.title}: {svc.display(user)} hat zugestimmt", "/stars")
    return svc.request_dict(req)


@router.post("/requests/{req_id}/decline")
async def decline_request(req_id: int, user: User = Depends(_parent), db: Session = Depends(get_db)):
    req = svc.decide_request(db, req_id, False, user)
    await _notify(req.user_id, "Belohnung abgelehnt", f"{req.title}: Deine Sterne bleiben erhalten", "/stars")
    return svc.request_dict(req)


@router.post("/requests/{req_id}/cancel")
def cancel_request(req_id: int, user: User = Depends(_member), db: Session = Depends(get_db)):
    return svc.request_dict(svc.cancel_request(db, req_id, user))


# --- history, confirmations, adjustments ---


@router.get("/ledger")
def ledger(user_id: Optional[int] = None, status: Optional[str] = None, user: User = Depends(_member),
           db: Session = Depends(get_db)):
    """History of one person. Parents may read anyone's, everyone else only their own."""
    target = user_id if user_id is not None else user.id
    if target != user.id and not svc.is_parent(user):
        raise HTTPException(403, "Nur der Verlauf der eigenen Sterne ist sichtbar")
    q = db.query(StarLedger).filter(StarLedger.user_id == target)
    if status:
        q = q.filter(StarLedger.status == status)
    rows = q.order_by(StarLedger.id.desc()).limit(200).all()
    return {"items": [svc.ledger_dict(e) for e in rows], **svc.account(db, target)}


@router.get("/pending")
def pending(_: User = Depends(_parent), db: Session = Depends(get_db)):
    """Everything waiting for a parent: reward requests and task completions to confirm."""
    reqs = db.query(StarRequest).filter(StarRequest.status == "pending").order_by(StarRequest.id).all()
    awards = (db.query(StarLedger).filter(StarLedger.kind == "task", StarLedger.status == "pending")
              .order_by(StarLedger.id).all())
    names = _names(db, {r.user_id for r in reqs} | {a.user_id for a in awards})
    return {"requests": [svc.request_dict(r, names.get(r.user_id, "")) for r in reqs],
            "awards": [svc.ledger_dict(a, names.get(a.user_id, "")) for a in awards]}


@router.post("/ledger/{entry_id}/confirm")
async def confirm_award(entry_id: int, user: User = Depends(_parent), db: Session = Depends(get_db)):
    entry = svc.decide_award(db, entry_id, True, user)
    await _notify(entry.user_id, "Sterne bestätigt", f"{entry.title}: +{entry.delta} ⭐", "/stars")
    return svc.ledger_dict(entry)


@router.post("/ledger/{entry_id}/reject")
def reject_award(entry_id: int, user: User = Depends(_parent), db: Session = Depends(get_db)):
    return svc.ledger_dict(svc.decide_award(db, entry_id, False, user))


@router.post("/adjust")
def adjust(body: AdjustIn, user: User = Depends(_parent), db: Session = Depends(get_db)):
    """Bonus or deduction by a parent; the balance cannot be pushed below what open requests reserve."""
    target = db.query(User).filter(User.id == body.user_id, User.is_active == True,  # noqa: E712
                                   User.role != "guest").first()
    if target is None:
        raise HTTPException(404, "Person nicht gefunden")
    if target.id == user.id:
        raise HTTPException(403, "Eigene Sterne kannst du nicht selbst ändern")
    return svc.adjust(db, target, body.delta, body.title, user)
