"""Benutzer- und Authentifizierungs-Modelle."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, LargeBinary, String, false

from app.core.database import Base

# Rollen im System. Jede Rolle besitzt eigene Rechte (siehe app/core/security.py).
ROLE_ADMIN = "admin"
ROLE_PARTNER = "partner"
ROLE_CHILD = "child"
ROLE_GUEST = "guest"
VALID_ROLES = {ROLE_ADMIN, ROLE_PARTNER, ROLE_CHILD, ROLE_GUEST}


class User(Base):
    """Benutzerkonto mit Rollenmodell."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    # Profil (selbst gepflegt): Anzeigename, Avatar-Farbe (#RRGGBB), Profilbild in user_avatars
    display_name = Column(String(40), nullable=True)
    avatar_color = Column(String(7), nullable=True)
    has_avatar = Column(Boolean, default=False, nullable=False, server_default=false())
    avatar_version = Column(Integer, default=0, nullable=False, server_default="0")

    # Where tasks that others assign to this person land: a task provider id, or NULL = derived from the
    # connected accounts (see app/services/task_routing.py)
    task_place = Column(String(32), nullable=True)
    language = Column(String(5), nullable=True)  # app language (de/en) for push texts; set from Accept-Language
    # Calendar synced on the phone (iOS/DAVx5): the phone alerts itself, the hub sends no event reminders
    calendar_on_phone = Column(Boolean, nullable=False, default=False, server_default=false())

    # Rolle: admin | partner | child | guest
    role = Column(String, default=ROLE_PARTNER, nullable=False)
    is_active = Column(Boolean, default=True)
    # is_admin bleibt für Abwärtskompatibilität erhalten und wird aus role abgeleitet.
    is_admin = Column(Boolean, default=False)

    # Optionale Verknüpfung zu einem Familienmitglied-Profil (Avatar, Farbe, ...)
    family_member_id = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)


    @property
    def effective_name(self) -> str:
        return self.display_name or self.full_name or self.username

    @property
    def avatar_url(self):
        # Version in der URL: neues Bild → neue URL, Clients laden neu
        return f"/api/users/{self.id}/avatar?v={self.avatar_version}" if self.has_avatar else None


class UserAvatar(Base):
    """Profilbild (klein, vom Client verkleinert; Typ serverseitig an der Signatur geprüft)."""

    __tablename__ = "user_avatars"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    content = Column(LargeBinary, nullable=False)
    mime = Column(String(20), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RefreshToken(Base):
    """Refresh-Token für Session-Management."""

    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    revoked = Column(Boolean, default=False)
    user_agent = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)


class LoginAttempt(Base):
    """Protokoll fehlgeschlagener/erfolgreicher Logins (Rate-Limiting)."""

    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True, nullable=False)
    ip_address = Column(String, index=True, nullable=False)
    success = Column(Boolean, default=False)
    attempted_at = Column(DateTime, default=datetime.utcnow, index=True)
