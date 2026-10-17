"""Legt den ersten Administrator an.

Nutzung (aus dem Verzeichnis ``backend/``):
    python -m scripts.create_admin                 # interaktiv
    python -m scripts.create_admin <user> <email> <passwort>
    HERMES_ADMIN_USER=... HERMES_ADMIN_EMAIL=... HERMES_ADMIN_PASSWORD=... python -m scripts.create_admin
"""

from __future__ import annotations

import getpass
import os
import sys

from app.core.database import SessionLocal, init_db
from app.core.security import get_password_hash
from app.models.user import ROLE_ADMIN, User


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        if len(sys.argv) >= 4:
            username, email, password = sys.argv[1], sys.argv[2], sys.argv[3]
        else:
            username = os.getenv("HERMES_ADMIN_USER") or _prompt("Benutzername", "admin")
            email = os.getenv("HERMES_ADMIN_EMAIL") or _prompt("E-Mail", "admin@example.com")
            password = os.getenv("HERMES_ADMIN_PASSWORD") or _prompt_password()

        if db.query(User).filter(User.username == username).first():
            print(f"Benutzer '{username}' existiert bereits.")
            return 1

        user = User(
            username=username,
            email=email,
            hashed_password=get_password_hash(password),
            full_name="Administrator",
            role=ROLE_ADMIN,
            is_admin=True,
        )
        db.add(user)
        db.commit()
        print(f"✅ Admin '{username}' wurde angelegt.")
        return 0
    finally:
        db.close()


def _prompt(label: str, default: str) -> str:
    if not sys.stdin.isatty():
        return default
    value = input(f"{label} [{default}]: ").strip()
    return value or default


def _prompt_password() -> str:
    if not sys.stdin.isatty():
        raise SystemExit("HERMES_ADMIN_PASSWORD muss gesetzt sein (kein TTY).")
    while True:
        pw = getpass.getpass("Passwort: ")
        if len(pw) < 6:
            print("Passwort muss mindestens 6 Zeichen haben.")
            continue
        if pw == getpass.getpass("Passwort wiederholen: "):
            return pw
        print("Passwörter stimmen nicht überein.")


if __name__ == "__main__":
    raise SystemExit(main())
