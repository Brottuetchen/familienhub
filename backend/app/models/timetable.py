"""Weekly timetable of a child: school lessons, sports, music, clubs."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base


class TimetableEntry(Base):
    __tablename__ = "timetable_entries"

    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    weekday = Column(Integer, nullable=False)  # 0 = Monday ... 6 = Sunday
    week = Column(String(3), nullable=False, default="all")  # all | a | b (A/B weeks)
    start = Column(String(5), nullable=False)  # local time "HH:MM"
    end = Column(String(5), nullable=False)
    title = Column(String(80), nullable=False)
    kind = Column(String(10), nullable=False, default="school")  # school | sport | music | club | other
    location = Column(String(80), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class TimetableSource(Base):
    """Which plugin provides the lessons of a child, and who the child is in the plugin's system."""

    __tablename__ = "timetable_sources"

    child_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    plugin_id = Column(String(40), nullable=False)
    person_id = Column(String(200), nullable=False)  # the plugin's own identifier of the person
    person_name = Column(String(120), nullable=True)  # label shown in the app (from ``timetable_people``)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
