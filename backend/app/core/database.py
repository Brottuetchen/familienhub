"""Datenbank-Setup (SQLAlchemy).

Standard ist SQLite (Zero-Config). Für Produktion kann via ``DATABASE_URL``
auf PostgreSQL umgestellt werden (siehe docker-compose.yml).
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect as sa_inspect
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger("core.database")

# …/backend/app/core/database.py -> parents[2] == backend/ (dort liegen alembic.ini + alembic/)
_BACKEND = Path(__file__).resolve().parents[2]

DATABASE_URL = settings.database_url

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def _alembic_config():
    """Alembic-Config ohne .ini (kein Logging-Hijack), mit App-URL + Skriptpfad."""
    from alembic.config import Config

    cfg = Config()  # ohne config_file_name -> env.py überspringt fileConfig
    cfg.set_main_option("script_location", str(_BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    return cfg


def redact_db_url(url: str) -> str:
    """Datenbank-URL ohne Passwort, z. B. für Logs."""
    from sqlalchemy.engine import make_url

    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:
        return "<ungültige DATABASE_URL>"


def init_db() -> None:
    """Bringt das Schema per Alembic auf ``head`` (idempotent, datensicher).

    - Frische DB: ``upgrade head`` legt alle Tabellen an.
    - Bestehende DB, die früher via ``create_all`` entstand (keine
      ``alembic_version``-Tabelle): zuerst auf die Baseline **stampen**, dann nur
      neuere Migrationen anwenden – so gehen keine Daten verloren.
    """
    from app import models  # noqa: F401  (registriert alle Tabellen an Base)
    from alembic import command
    from alembic.script import ScriptDirectory

    cfg = _alembic_config()
    insp = sa_inspect(engine)
    if insp.has_table("users") and not insp.has_table("alembic_version"):
        base_rev = ScriptDirectory.from_config(cfg).get_bases()[0]
        logger.info("Bestehende DB erkannt – stampe Baseline-Revision %s", base_rev)
        command.stamp(cfg, base_rev)
    command.upgrade(cfg, "head")


def get_db():
    """FastAPI-Dependency für eine DB-Session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
