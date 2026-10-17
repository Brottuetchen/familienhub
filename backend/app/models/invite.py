"""Einladung (#B): Admin lädt eine Person ein; sie setzt mit dem Code ihr eigenes Passwort.

Gespeichert wird nur der SHA-256 des Codes. Ein Code gilt 7 Tage und genau einmal.
"""

import hashlib
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base


class Invite(Base):
    __tablename__ = "invites"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    code_hash = Column(String(64), nullable=False, unique=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)

    @staticmethod
    def hash(code: str) -> str:
        return hashlib.sha256(code.encode()).hexdigest()
