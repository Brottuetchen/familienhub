"""Persönliche Zugangsschlüssel für Assistenten (z. B. Sprachassistenten).

Jede Person legt ihre eigenen Schlüssel an; ein Schlüssel handelt nur als diese Person.
Gespeichert wird nur der SHA-256-Hash, der Klartext wird genau einmal angezeigt.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base

TOKEN_PREFIX = "fhp_"


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    hint = Column(String, nullable=False)  # erste Zeichen zum Wiedererkennen
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)

    @staticmethod
    def hash(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def generate() -> str:
        return TOKEN_PREFIX + secrets.token_urlsafe(32)
