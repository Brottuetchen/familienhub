"""Birthdays and anniversaries of family, relatives and friends, with gift ideas per entry."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base


class Birthday(Base):
    __tablename__ = "birthdays"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    kind = Column(String(16), nullable=False, default="birthday")  # birthday | anniversary
    month = Column(Integer, nullable=False)
    day = Column(Integer, nullable=False)
    year = Column(Integer, nullable=True)  # optional: without it no age/years are shown
    # Linked hub user: this person never sees the gift ideas (enforced server-side)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    # Notify this many days before (0 = on the day); None = no reminder
    remind_days_before = Column(Integer, nullable=True, default=7)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class GiftIdea(Base):
    __tablename__ = "gift_ideas"

    id = Column(Integer, primary_key=True)
    birthday_id = Column(Integer, ForeignKey("birthdays.id", ondelete="CASCADE"), nullable=False, index=True)
    text = Column(String(300), nullable=False)
    link = Column(String(500), nullable=True)
    done = Column(Boolean, nullable=False, default=False)  # already bought / given
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
