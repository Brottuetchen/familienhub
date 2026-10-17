"""Persönliche native Auswahl und dauerhafte Nicht-Replay-Belege (#47)."""
from sqlalchemy import Column, ForeignKey, Integer, String, Text, UniqueConstraint, JSON
from app.core.database import Base


class HabiticaAccount(Base):
    __tablename__ = "habitica_accounts"
    __table_args__ = (UniqueConstraint("server_url", "remote_user_id"),)
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    server_url = Column(String, nullable=False)
    remote_user_id = Column(String, nullable=False)
    api_key_enc = Column(Text, nullable=False)
    pending_operation = Column(String, nullable=True)


class HabiticaSelection(Base):
    __tablename__ = "habitica_selections"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    account_ref = Column(String, primary_key=True)
    remote_id = Column(String, primary_key=True)


class HabiticaOperation(Base):
    __tablename__ = "habitica_operations"
    key = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    account_ref = Column(String, nullable=False)
    fingerprint = Column(String, nullable=False)
    state = Column(String, nullable=False, default="pending")
    result = Column(JSON, nullable=True)
