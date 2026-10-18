"""Rückmeldungen aus der App (Beta): Text, Version, Plattform, Bereich. Admins sehen sie in der Verwaltung."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    text = Column(Text, nullable=False)
    area = Column(String(40), nullable=True)
    app_version = Column(String(40), nullable=True)
    platform = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    done_at = Column(DateTime, nullable=True)
