"""Persönlicher Paperless-Zugang (jede Person ihr eigenes API-Token, verschlüsselt)."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class PaperlessAccount(Base):
    __tablename__ = "paperless_accounts"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    token_enc = Column(Text, nullable=False)
    remote_username = Column(String(150), nullable=True)
    verified_at = Column(DateTime, default=datetime.utcnow, nullable=False)
