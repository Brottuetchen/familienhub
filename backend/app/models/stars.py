"""Kids mode: stars for tasks and rewards.

Stars are kept hub-side for every task source, keyed by ``(provider, task uid)``. The per-person balance lives in
``star_accounts`` and is only changed with conditional UPDATEs, so it can never go negative, not even with
concurrent requests. ``star_ledger`` is the history.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text,
                        UniqueConstraint)

from app.core.database import Base


class StarTask(Base):
    """How many stars completing this task is worth."""

    __tablename__ = "star_tasks"

    provider = Column(String(32), primary_key=True)
    task_uid = Column(String(255), primary_key=True)
    stars = Column(Integer, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class StarAccount(Base):
    """Confirmed balance and the part reserved by open reward requests."""

    __tablename__ = "star_accounts"
    __table_args__ = (CheckConstraint("balance >= 0 AND reserved >= 0 AND reserved <= balance",
                                      name="ck_star_account_not_negative"),)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    balance = Column(Integer, nullable=False, default=0)
    reserved = Column(Integer, nullable=False, default=0)


class StarLedger(Base):
    """History per person: task awards (pending until a parent confirms, if required), rewards, adjustments."""

    __tablename__ = "star_ledger"
    __table_args__ = (UniqueConstraint("user_id", "kind", "ref", name="uq_star_ledger_ref"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    delta = Column(Integer, nullable=False)
    kind = Column(String(16), nullable=False)  # task | reward | adjust
    status = Column(String(16), nullable=False, default="confirmed")  # pending | confirmed | rejected
    title = Column(String(200), nullable=False, default="")
    ref = Column(String(300), nullable=False)  # idempotency key, e.g. "provider:uid:due" or "request:5"
    decided_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    decided_at = Column(DateTime, nullable=True)


class StarReward(Base):
    __tablename__ = "star_rewards"

    id = Column(Integer, primary_key=True)
    title = Column(String(120), nullable=False)
    price = Column(Integer, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class StarRequest(Base):
    """A child asks for a reward. Title and price are copied, so later edits do not change old requests."""

    __tablename__ = "star_requests"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    reward_id = Column(Integer, ForeignKey("star_rewards.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(120), nullable=False)
    price = Column(Integer, nullable=False)
    status = Column(String(16), nullable=False, default="pending")  # pending | approved | declined | cancelled
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    decided_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime, nullable=True)
