"""Verlauf: jede Mitteilung an eine Person (auch wenn Ruhezeit den Push unterdrückt hat)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class NotificationLog(Base):
    __tablename__ = "notification_log"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=True)
    category = Column(String, nullable=False, default="system")
    route = Column(String, nullable=True)
    source = Column(String, nullable=False, default="hub")  # hub | Name des Dienst-Schlüssels
    delivered = Column(Integer, nullable=False, default=0)  # Anzahl Geräte, die den Push bekamen
    suppressed = Column(Boolean, nullable=False, default=False)  # Ruhezeit/Kategorie aus
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    read_at = Column(DateTime, nullable=True)
