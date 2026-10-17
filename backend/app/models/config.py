"""Laufzeit-Konfiguration (vom Admin im UI editierbar).

Überschreibt einzelne ``settings``-Felder (z.B. Connector-URLs/Tokens) ohne
`.env`-Bearbeitung oder Neustart. Secrets werden verschlüsselt abgelegt.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String, Text

from app.core.database import Base


class ConfigOverride(Base):
    __tablename__ = "config_overrides"

    # entspricht einem settings-Feldnamen, z.B. "vikunja_url", "vikunja_token"
    key = Column(String(100), primary_key=True)
    # Klartext (nicht-secret) oder Fernet-verschlüsselt (secret=True)
    value = Column(Text, nullable=False, default="")
    secret = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
