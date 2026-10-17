"""Dienst-Schlüssel: andere Systeme (Home Assistant, Shelfarr, …) dürfen damit nur Mitteilungen einliefern."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from app.core.database import Base

SERVICE_KEY_PREFIX = "fhs_"


class ServiceKey(Base):
    __tablename__ = "service_keys"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)  # erscheint als Quelle im Verlauf
    key_hash = Column(String, nullable=False, unique=True, index=True)
    hint = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)

    @staticmethod
    def hash(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def generate() -> str:
        return SERVICE_KEY_PREFIX + secrets.token_urlsafe(32)
