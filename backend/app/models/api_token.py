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

# Scopes for the voice endpoints (``/api/voice``); the preset "voice" stands for all of them.
VOICE_SCOPES = ("shopping:read", "shopping:write", "tasks:write", "meals:read", "calendar:read", "reminders:write")

# Scopes for the normal API, one read and one write scope per area. They live in their own ``api:`` namespace so
# that existing voice keys (``shopping:read`` ...) do not suddenly reach the normal API.
API_AREAS = ("today", "tasks", "shopping", "calendar", "meals", "reminders", "notifications", "documents", "books", "media")
API_READ_SCOPES = tuple(f"api:{a}:read" for a in API_AREAS)
API_WRITE_SCOPES = tuple(f"api:{a}:write" for a in API_AREAS)
API_SCOPES = API_READ_SCOPES + API_WRITE_SCOPES
ALL_SCOPES = VOICE_SCOPES + API_SCOPES
SCOPE_PRESETS = {"voice": VOICE_SCOPES, "read": API_READ_SCOPES}

# Explicit allow-list of normal-API routes a scoped key may call: (method, route template) -> scope.
# Everything not listed (admin, key management, profile, accounts, webhooks ...) is closed to scoped keys.
_R = {
    "today": [("GET", "/api/today")],
    "tasks": [("GET", "/api/tasks"), ("GET", "/api/tasks/lists"), ("GET", "/api/tasks/providers")],
    "shopping": [("GET", "/api/shopping"), ("GET", "/api/shopping/recent")],
    "calendar": [("GET", "/api/calendar/today"), ("GET", "/api/calendar/events"), ("GET", "/api/calendar/calendars"),
                 ("GET", "/api/calendar/holidays")],
    "meals": [("GET", "/api/meals"), ("GET", "/api/meals/plan")],
    "reminders": [("GET", "/api/reminders")],
    "notifications": [("GET", "/api/me/notifications")],
    "documents": [("GET", "/api/paperless/recent"), ("GET", "/api/paperless/search"), ("GET", "/api/paperless/deadlines")],
    "books": [("GET", "/api/books/search"), ("GET", "/api/books/discover"), ("GET", "/api/books/requests")],
    "media": [("GET", "/api/media/search"), ("GET", "/api/media/requests")],
}
_W = {
    "tasks": [("POST", "/api/tasks"), ("PATCH", "/api/tasks/{uid}"), ("POST", "/api/tasks/{uid}/complete"),
              ("DELETE", "/api/tasks/{uid}")],
    "shopping": [("POST", "/api/shopping"), ("PATCH", "/api/shopping/{uid}"), ("DELETE", "/api/shopping/{uid}")],
    "calendar": [("POST", "/api/calendar/events"), ("PUT", "/api/calendar/events/{event_id}"),
                 ("DELETE", "/api/calendar/events/{event_id}")],
    "meals": [("POST", "/api/meals/plan"), ("DELETE", "/api/meals/plan/{entry_id}"), ("PATCH", "/api/meals/{meal_id}"),
              ("DELETE", "/api/meals/{meal_id}")],
    "reminders": [("POST", "/api/reminders"), ("PATCH", "/api/reminders/{reminder_id}"),
                  ("POST", "/api/reminders/{reminder_id}/snooze"), ("POST", "/api/reminders/{reminder_id}/action"),
                  ("DELETE", "/api/reminders/{reminder_id}")],
    "notifications": [("POST", "/api/me/notifications/read")],
    "documents": [("POST", "/api/paperless/deadlines/{doc_id}/remind")],
    "books": [("POST", "/api/books/requests"), ("DELETE", "/api/books/requests/{request_id}")],
    "media": [("POST", "/api/media/requests"), ("DELETE", "/api/media/requests/{request_id}")],
}
API_ROUTE_SCOPES = {
    **{r: f"api:{a}:read" for a, routes in _R.items() for r in routes},
    **{r: f"api:{a}:write" for a, routes in _W.items() for r in routes},
}


def normalize_scopes(wanted):
    """Expand presets, add the read scope to every write scope (write implies read), drop duplicates."""
    out = []
    for s in wanted:
        out.extend(SCOPE_PRESETS.get(s, (s,)))
    for s in list(out):
        if s.startswith("api:") and s.endswith(":write"):
            out.append(s[:-len("write")] + "read")
    return list(dict.fromkeys(out))


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
    # Space-separated scope names; NULL = unrestricted (keys from before scopes). Scoped keys only reach /api/voice.
    scopes = Column(String, nullable=True)

    @property
    def scope_list(self):
        return None if self.scopes is None else self.scopes.split()

    @staticmethod
    def hash(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def generate() -> str:
        return TOKEN_PREFIX + secrets.token_urlsafe(32)
