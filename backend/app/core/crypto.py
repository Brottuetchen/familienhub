"""Symmetrische Verschlüsselung für sensible Laufzeit-Einstellungen (Tokens, Passwörter).

Der Schlüssel wird deterministisch aus ``SECRET_KEY`` abgeleitet (Fernet). So liegen
Tokens NICHT im Klartext in der DB. Ändert sich ``SECRET_KEY``, sind alte Werte nicht
mehr entschlüsselbar (dann einfach neu eintragen).
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger("core.crypto")


def _fernet() -> Fernet:
    digest = hashlib.sha256((settings.secret_key or "").encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plaintext: str) -> str:
    if plaintext is None:
        plaintext = ""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError) as exc:
        logger.warning("Konnte einen verschlüsselten Wert nicht entschlüsseln: %s", exc)
        return ""
