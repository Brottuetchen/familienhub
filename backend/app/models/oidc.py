"""OIDC-Authentifizierungs-Modelle."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.core.database import Base


class OIDCSession(Base):
    """Temporäre OIDC-Session-Daten für Authorization Code Flow."""

    __tablename__ = "oidc_sessions"

    id = Column(Integer, primary_key=True, index=True)
    state = Column(String, unique=True, index=True, nullable=False)
    nonce = Column(String, nullable=False)
    code_verifier = Column(String, nullable=False)
    client_type = Column(String, nullable=False)  # 'web' oder 'app'
    app_challenge = Column(String, nullable=True)  # PKCE-Bindung des Rücksprungs an das startende Gerät
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class OIDCExchangeCode(Base):
    """Einmal-Exchange-Code für App-Login (60s gültig)."""

    __tablename__ = "oidc_exchange_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    app_challenge = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
