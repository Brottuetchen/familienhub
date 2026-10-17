"""Logging-Setup für Hermes."""

import logging

from app.config import settings


def setup_logging() -> None:
    """Konfiguriert das Root-Logging anhand des konfigurierten Levels."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    from app.core import log_buffer

    log_buffer.install()  # Warnungen/Fehler fürs Protokoll in der Verwaltung


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
