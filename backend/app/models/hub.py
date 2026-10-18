"""Built-in sources: tasks, shopping list and family calendar stored in the hub's own database."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class HubTask(Base):
    __tablename__ = "hub_tasks"

    uid = Column(String(64), primary_key=True)
    title = Column(String(200), nullable=False)
    notes = Column(Text, nullable=False, default="")
    due = Column(String(32), nullable=True)  # "YYYY-MM-DD" or ISO date-time, as the app sends it
    priority = Column(Integer, nullable=True)
    done = Column(Boolean, nullable=False, default=False)
    completed_at = Column(DateTime, nullable=True)
    family = Column(Boolean, nullable=False, default=False)  # family list: visible to everyone
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    # Personal tasks belong to the assignee (or the creator); family tasks may have an assignee too.
    assignee_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    recurrence = Column(String(16), nullable=False, default="none")
    rotation = Column(JSON, nullable=False, default=list)
    successor_uid = Column(String(64), nullable=True)  # set once a household task has created its next turn
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class HubShoppingItem(Base):
    __tablename__ = "hub_shopping_items"

    id = Column(Integer, primary_key=True)
    summary = Column(String(200), nullable=False)
    done = Column(Boolean, nullable=False, default=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)


class HubEvent(Base):
    __tablename__ = "hub_events"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    start = Column(DateTime, nullable=False, index=True)  # local wall time, like the app sends it
    end = Column(DateTime, nullable=False)
    all_day = Column(Boolean, nullable=False, default=False)
    location = Column(String(200), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
