"""Push-Geräte-Modell (FCM + Web Push)."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.core.database import Base


class PushDevice(Base):
    """Push-fähiges Gerät (FCM oder Web Push)."""

    __tablename__ = "push_devices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    kind = Column(String, nullable=False)  # fcm | webpush
    token = Column(Text, nullable=False)  # FCM token oder WebPush subscription JSON
    device_name = Column(String, nullable=True)
    last_seen = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
