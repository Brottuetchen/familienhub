"""Benachrichtigungseinstellungen pro Nutzer und Kategorie."""


from sqlalchemy import Boolean, Column, Integer, String, Time

from app.core.database import Base


class NotificationPreference(Base):
    """Benachrichtigungseinstellungen (Ruhezeiten, Kategorien)."""

    __tablename__ = "notification_prefs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    category = Column(String, nullable=False)  # all | task_assigned | info | system | ...
    enabled = Column(Boolean, default=True, nullable=False)
    quiet_start = Column(Time, nullable=True)  # z.B. 22:00
    quiet_end = Column(Time, nullable=True)    # z.B. 08:00
