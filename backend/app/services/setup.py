"""Ersteinrichtung (#4): Solange es keinen aktiven Admin gibt, darf genau einmal ein Admin angelegt werden.

Standard: Wer den Hub zuerst öffnet, legt den Admin an. Mit SETUP_REQUIRE_CODE=true schützt ein
Einrichtungscode (nur im Server-Log sichtbar); nach zehn falschen Versuchen gibt es einen neuen Code.
Mit dem ersten Admin ist die Einrichtung vorbei.
"""

from __future__ import annotations

import hmac
import logging
import secrets
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings

from app.models.user import ROLE_ADMIN, User

logger = logging.getLogger("familienhub.setup")

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # ohne 0/O, 1/I
MAX_ATTEMPTS = 10

_code: Optional[str] = None
_attempts = 0


def needs_setup(db: Session) -> bool:
    return db.query(User).filter(User.role == ROLE_ADMIN, User.is_active == True).count() == 0  # noqa: E712


def _normalize(code: str) -> str:
    return "".join(ch for ch in (code or "").upper() if ch in ALPHABET)


def new_code() -> str:
    global _code, _attempts
    raw = "".join(secrets.choice(ALPHABET) for _ in range(8))
    _code, _attempts = raw, 0
    logger.warning("Setup is open - setup code: %s-%s (enter it in the app on the setup screen)", raw[:4], raw[4:])
    return f"{raw[:4]}-{raw[4:]}"


def prepare(db: Session) -> None:
    """Beim Start: Code nur erzeugen, wenn noch kein Admin existiert."""
    global _code
    _code = None
    if not needs_setup(db):
        return
    if settings.setup_require_code:
        new_code()
    else:
        logger.warning(
            "Setup is open: the first person to open the hub becomes admin. "
            "Set SETUP_REQUIRE_CODE=true if the hub is reachable from the internet before setup."
        )


def code_required() -> bool:
    return bool(settings.setup_require_code)


def check_code(code: str | None) -> bool:
    global _attempts
    if not code_required():
        return True
    code = code or ""
    if not _code:
        return False
    if hmac.compare_digest(_normalize(code), _code):
        return True
    _attempts += 1
    if _attempts >= MAX_ATTEMPTS:
        logger.warning("Too many wrong setup codes - generating a new code")
        new_code()
    return False


def finish() -> None:
    global _code
    _code = None
