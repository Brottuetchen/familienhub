"""Kids mode: stars for tasks and rewards (balance, awards, reward requests).

Rules that hold under concurrent requests:
- the balance only changes through conditional ``UPDATE`` statements, so it never goes below zero and never
  below what open reward requests have reserved (the table also carries a CHECK constraint);
- every state change of a request or an award is a compare-and-set on its status, so two parents approving
  the same request at once produce exactly one booking;
- an award is unique per person and task occurrence (unique ledger reference), so completing twice pays once.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models.config import ConfigOverride
from app.models.stars import StarAccount, StarLedger, StarRequest, StarReward, StarTask
from app.models.user import ROLE_ADMIN, ROLE_CHILD, ROLE_PARTNER, User

logger = get_logger("service.stars")

CONFIRM_KEY = "STARS_CONFIRM_TASKS"
MAX_TASK_STARS = 100
MAX_PRICE = 100000
MAX_ADJUST = 1000


def is_parent(user: User) -> bool:
    return bool(user.is_admin or user.role in (ROLE_ADMIN, ROLE_PARTNER))


def parents(db: Session) -> List[User]:
    return [u for u in db.query(User).filter(User.is_active == True).all() if is_parent(u)]  # noqa: E712


def display(user: Optional[User]) -> str:
    return (user.full_name or user.username) if user else ""


# --- settings ---


def confirm_required(db: Session) -> bool:
    row = db.get(ConfigOverride, CONFIRM_KEY)
    return bool(row and row.value == "1")


def set_confirm_required(db: Session, value: bool) -> None:
    row = db.get(ConfigOverride, CONFIRM_KEY) or ConfigOverride(key=CONFIRM_KEY)
    row.value, row.secret = "1" if value else "0", False
    db.add(row)
    db.commit()


# --- accounts ---


def ensure_account(db: Session, user_id: int) -> None:
    if db.get(StarAccount, user_id) is not None:
        return
    try:
        with db.begin_nested():
            db.add(StarAccount(user_id=user_id, balance=0, reserved=0))
    except IntegrityError:  # created concurrently
        pass


def account(db: Session, user_id: int) -> Dict[str, int]:
    row = db.get(StarAccount, user_id)
    if row is not None:
        db.refresh(row)
    balance, reserved = (row.balance, row.reserved) if row else (0, 0)
    return {"balance": balance, "reserved": reserved, "available": balance - reserved}


def _credit(db: Session, user_id: int, amount: int) -> None:
    ensure_account(db, user_id)
    db.execute(update(StarAccount).where(StarAccount.user_id == user_id)
               .values(balance=StarAccount.balance + amount))


# --- stars on tasks ---


def set_task_stars(db: Session, provider: str, uid: str, stars: int, user: User) -> int:
    row = db.get(StarTask, (provider, uid))
    if stars <= 0:
        if row is not None:
            db.delete(row)
    elif row is None:
        db.add(StarTask(provider=provider, task_uid=uid, stars=stars, created_by=user.id))
    else:
        row.stars = stars
    db.commit()
    return max(stars, 0)


def attach_stars(db: Session, items: List[Any]) -> None:
    """Adds ``stars`` to task dicts that carry some. Never raises: stars are optional decoration."""
    try:
        tasks = [t for t in items if isinstance(t, dict) and t.get("uid")]
        if not tasks:
            return
        rows = db.query(StarTask).filter(StarTask.task_uid.in_({str(t["uid"]) for t in tasks})).all()
        found = {(r.provider, r.task_uid): r.stars for r in rows}
        for t in tasks:
            value = found.get((t.get("provider"), str(t["uid"])))
            if value:
                t["stars"] = value
    except Exception:  # noqa: BLE001
        logger.warning("stars could not be read", exc_info=True)


def award_for_completion(db: Session, user: User, provider: str, uid: str, result: Any) -> Optional[Dict[str, Any]]:
    """Pays the stars of a completed task to the person who completed it. ``None`` when nothing was paid."""
    cfg = db.get(StarTask, (provider, uid))
    if cfg is None or cfg.stars <= 0 or user.role == "guest":
        return None
    occurrence = str(result.get("due") or "") if isinstance(result, dict) else ""
    title = str(result.get("title") or "") if isinstance(result, dict) else ""
    pending = user.role == ROLE_CHILD and not is_parent(user) and confirm_required(db)
    entry = StarLedger(user_id=user.id, delta=cfg.stars, kind="task", title=title[:200],
                       status="pending" if pending else "confirmed", ref=f"{provider}:{uid}:{occurrence}"[:300])
    try:
        with db.begin_nested():
            db.add(entry)
            db.flush()
    except IntegrityError:  # already paid for this occurrence
        return None
    if not pending:
        _credit(db, user.id, cfg.stars)
    db.commit()
    return {"stars": cfg.stars, "status": entry.status, "ledger_id": entry.id, "title": title}


def carry_to_successor(db: Session, provider: str, uid: str, successor: Optional[str]) -> None:
    """A rotating household task creates the next turn under a new uid: the next turn is worth the same."""
    cfg = db.get(StarTask, (provider, uid))
    if cfg is not None and successor and db.get(StarTask, (provider, successor)) is None:
        db.add(StarTask(provider=provider, task_uid=successor, stars=cfg.stars, created_by=cfg.created_by))
        db.commit()


def decide_award(db: Session, entry_id: int, approve: bool, parent: User) -> StarLedger:
    entry = db.get(StarLedger, entry_id)
    if entry is None or entry.kind != "task":
        raise HTTPException(404, "Eintrag nicht gefunden")
    if entry.user_id == parent.id:
        raise HTTPException(403, "Eigene Sterne kannst du nicht selbst bestätigen")
    new = "confirmed" if approve else "rejected"
    moved = db.execute(update(StarLedger).where(StarLedger.id == entry_id, StarLedger.status == "pending")
                       .values(status=new, decided_by=parent.id, decided_at=datetime.utcnow())).rowcount
    if not moved:
        db.rollback()
        raise HTTPException(409, "Dieser Eintrag wurde bereits entschieden")
    if approve:
        _credit(db, entry.user_id, entry.delta)
    db.commit()
    db.refresh(entry)
    return entry


def adjust(db: Session, target: User, delta: int, title: str, parent: User) -> Dict[str, int]:
    if delta == 0 or abs(delta) > MAX_ADJUST:
        raise HTTPException(422, "Ungültige Anzahl Sterne")
    ensure_account(db, target.id)
    if delta < 0:
        ok = db.execute(update(StarAccount).where(
            StarAccount.user_id == target.id, StarAccount.balance + delta >= StarAccount.reserved)
            .values(balance=StarAccount.balance + delta)).rowcount
        if not ok:
            db.rollback()
            raise HTTPException(409, "Nicht genug Sterne")
    else:
        _credit(db, target.id, delta)
    db.add(StarLedger(user_id=target.id, delta=delta, kind="adjust", status="confirmed", title=title[:200],
                      ref=f"adjust:{uuid.uuid4()}", decided_by=parent.id, decided_at=datetime.utcnow()))
    db.commit()
    return account(db, target.id)


# --- rewards ---


def create_reward(db: Session, title: str, price: int, user: User) -> StarReward:
    reward = StarReward(title=title.strip()[:120], price=price, active=True, created_by=user.id)
    db.add(reward)
    db.commit()
    return reward


def request_reward(db: Session, user: User, reward_id: int) -> StarRequest:
    reward = db.get(StarReward, reward_id)
    if reward is None or not reward.active:
        raise HTTPException(404, "Belohnung nicht gefunden")
    ensure_account(db, user.id)
    req = StarRequest(user_id=user.id, reward_id=reward.id, title=reward.title, price=reward.price, status="pending")
    db.add(req)
    db.flush()
    reserved = db.execute(update(StarAccount).where(
        StarAccount.user_id == user.id, StarAccount.balance - StarAccount.reserved >= reward.price)
        .values(reserved=StarAccount.reserved + reward.price)).rowcount
    if not reserved:
        db.rollback()
        raise HTTPException(409, "Nicht genug Sterne")
    db.commit()
    return req


def _close(db: Session, req_id: int, status: str, who: User, only_owner: Optional[int] = None) -> StarRequest:
    req = db.get(StarRequest, req_id)
    if req is None or (only_owner is not None and req.user_id != only_owner):
        raise HTTPException(404, "Anfrage nicht gefunden")
    moved = db.execute(update(StarRequest).where(StarRequest.id == req_id, StarRequest.status == "pending").values(
        status=status, decided_by=who.id, decided_at=datetime.utcnow())).rowcount
    if not moved:
        db.rollback()
        raise HTTPException(409, "Diese Anfrage wurde bereits entschieden")
    if status == "approved":
        paid = db.execute(update(StarAccount).where(
            StarAccount.user_id == req.user_id, StarAccount.reserved >= req.price, StarAccount.balance >= req.price)
            .values(balance=StarAccount.balance - req.price, reserved=StarAccount.reserved - req.price)).rowcount
        if not paid:
            db.rollback()
            raise HTTPException(409, "Nicht genug Sterne")
        db.add(StarLedger(user_id=req.user_id, delta=-req.price, kind="reward", status="confirmed",
                          title=req.title, ref=f"request:{req.id}", decided_by=who.id, decided_at=datetime.utcnow()))
    else:
        db.execute(update(StarAccount).where(StarAccount.user_id == req.user_id, StarAccount.reserved >= req.price)
                   .values(reserved=StarAccount.reserved - req.price))
    db.commit()
    db.refresh(req)
    return req


def decide_request(db: Session, req_id: int, approve: bool, parent: User) -> StarRequest:
    req = db.get(StarRequest, req_id)
    if req is not None and req.user_id == parent.id:
        raise HTTPException(403, "Eigene Anfragen kannst du nicht selbst entscheiden")
    return _close(db, req_id, "approved" if approve else "declined", parent)


def cancel_request(db: Session, req_id: int, user: User) -> StarRequest:
    return _close(db, req_id, "cancelled", user, only_owner=user.id)


# --- reading ---


def pending_counts(db: Session) -> Dict[str, int]:
    requests = db.query(StarRequest).filter(StarRequest.status == "pending").count()
    awards = db.query(StarLedger).filter(StarLedger.kind == "task", StarLedger.status == "pending").count()
    return {"requests": requests, "awards": awards, "total": requests + awards}


def uses_stars(db: Session, user: User) -> bool:
    """Does this person take part in the stars feature? Decides whether Today shows the card."""
    if user.role == "guest":
        return False
    if db.get(StarAccount, user.id) is not None:
        return True
    if is_parent(user):
        return pending_counts(db)["total"] > 0
    return user.role == ROLE_CHILD and db.query(StarReward).filter(StarReward.active == True).count() > 0  # noqa: E712


def next_reward(db: Session, available: int) -> Optional[Dict[str, Any]]:
    """The cheapest reward still out of reach, else the most expensive one (everything is affordable)."""
    rewards = db.query(StarReward).filter(StarReward.active == True).order_by(  # noqa: E712
        StarReward.price, StarReward.id).all()
    if not rewards:
        return None
    target = next((r for r in rewards if r.price > available), rewards[-1])
    return {"id": target.id, "title": target.title, "price": target.price, "missing": max(target.price - available, 0)}


def summary(db: Session, user: User) -> Dict[str, Any]:
    acct = account(db, user.id)
    enabled = uses_stars(db, user)
    out: Dict[str, Any] = {"enabled": enabled, **acct,
                           "next_reward": next_reward(db, acct["available"]) if enabled else None}
    if is_parent(user):
        out["pending"] = pending_counts(db)
    return out


def reward_dict(r: StarReward, parent: bool = False) -> Dict[str, Any]:
    """``parent`` adds the plugin action (with its parameter values), which only parents get to see."""
    out = {"id": r.id, "title": r.title, "price": r.price, "active": bool(r.active)}
    if parent:
        from app.services import reward_actions

        out["action"] = reward_actions.action_view(r)
    return out


def request_dict(r: StarRequest, name: str = "") -> Dict[str, Any]:
    return {"id": r.id, "user_id": r.user_id, "user_name": name, "reward_id": r.reward_id, "title": r.title,
            "price": r.price, "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "decided_at": r.decided_at.isoformat() if r.decided_at else None}


def ledger_dict(e: StarLedger, name: str = "") -> Dict[str, Any]:
    return {"id": e.id, "user_id": e.user_id, "user_name": name, "delta": e.delta, "kind": e.kind,
            "status": e.status, "title": e.title,
            "created_at": e.created_at.isoformat() if e.created_at else None}
