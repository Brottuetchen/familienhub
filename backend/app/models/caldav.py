"""Modelle für CalDAV-Integration (Nextcloud Tasks)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base


class CalDAVAccount(Base):
    """CalDAV-Account pro Nutzer (Nextcloud)."""

    __tablename__ = "caldav_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    url = Column(String, nullable=False)
    username = Column(String, nullable=False)
    password_enc = Column(String, nullable=False)  # verschlüsselt via crypto.py
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TaskList(Base):
    """Zuordnung CalDAV-Listen zu Hub-Nutzern."""

    __tablename__ = "task_lists"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)  # wer hat Zugriff
    caldav_url = Column(String, unique=True, nullable=False, index=True)  # URL der CalDAV-Liste
    display_name = Column(String, nullable=False)
    kind = Column(String, nullable=False)  # personal | family | hidden
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # bei family = NULL
