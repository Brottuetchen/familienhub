"""Hermes-eigene Erinnerungen.

Erinnerungen sind einer der wenigen Datentypen, die Hermes selbst speichert
(statt sie an ein Fachsystem zu delegieren) – etwa "Heute Abend an den Müll
denken". Sie werden im Dashboard und über Push ausgespielt.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, false, or_

from app.core.database import Base


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    notes = Column(Text, nullable=True)
    due_at = Column(DateTime, nullable=True, index=True)
    # Priorität: critical | important | info
    priority = Column(String, default="info")
    # Wiederholung: none | daily | weekdays | weekly | monthly
    recurrence = Column(String, default="none")
    # Quelle: user | ai | connector:<name>
    source = Column(String, default="user")
    completed = Column(Boolean, default=False)
    notified = Column(Boolean, default=False)

    family_member_id = Column(Integer, nullable=True)
    created_by = Column(Integer, nullable=True)  # user id
    # False: nur für den Ersteller. True: alle sehen sie und bekommen die Mitteilung.
    for_family = Column(Boolean, default=False, nullable=False, server_default=false())
    # Auslöser: time (due_at) | arrival (wenn die Person nach Hause kommt, meldet Home Assistant)
    fire_on = Column(String, default="time", nullable=False, server_default="time")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def visible_to(user_id: int):
    """Filter: eigene Erinnerungen, Familien-Erinnerungen und alte ohne Ersteller."""
    return or_(Reminder.for_family == True, Reminder.created_by == user_id, Reminder.created_by.is_(None))  # noqa: E712
