"""Per-person ntfy delivery target. The server address is set by the admin (plugin setting), never per person."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base


class NtfyTarget(Base):
    __tablename__ = "ntfy_targets"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    # The topic is the secret: whoever knows it can read the messages if the server allows anonymous reading.
    topic = Column(String(64), nullable=False, unique=True)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
