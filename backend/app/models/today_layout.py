"""Per-person arrangement of the "Today" screen (the family default lives in ``config_overrides``)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text

from app.core.database import Base


class TodayLayout(Base):
    __tablename__ = "today_layouts"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    # JSON list of {"id", "visible", "size"}
    layout = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
