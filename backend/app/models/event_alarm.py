"""Event reminders already sent by the hub (one notification per person, event occurrence and alarm)."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint

from app.core.database import Base


class EventAlarmSent(Base):
    __tablename__ = "event_alarms_sent"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_event_alarm_user_key"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(300), nullable=False)  # calendar | uid | start | minutes
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
