"""Laufzeit-Konfiguration: Admin-editierbare Plugin-Einstellungen (URLs/Tokens).

Overrides liegen in ``config_overrides`` und gelten sofort, ohne `.env`-Bearbeitung
oder Neustart. Welche Schlüssel erlaubt sind und welche geheim sind, bestimmen die
Plugins (``Plugin.settings``). Secrets werden verschlüsselt gespeichert und nie im
Klartext zurückgegeben.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.core.crypto import decrypt, encrypt
from app.core.logging_config import get_logger
from app.models.config import ConfigOverride

logger = get_logger("service.config_store")

# Overrides für Plugin-Einstellungen ohne Feld in den Kern-Settings (z. B. externe Plugins)
_extra: Dict[str, str] = {}


def get_override(key: str) -> Optional[str]:
    return _extra.get(key.upper())


def _core_settings():
    """Allgemeine Einstellungen aus dem Einrichtungs-Assistenten (keine Plugins)."""
    from app.plugins.base import Setting

    return (Setting("APP_NAME", "Name des Hubs"), Setting("TIMEZONE", "Zeitzone"),
            # Sources per area (Administration → Sources): one source for shopping, a selection for tasks/calendar
            Setting("SHOPPING_SOURCE", "Einkauf aus", required=False),
            Setting("TASKS_SOURCES", "Aufgaben aus", required=False),
            Setting("CALENDAR_SOURCES", "Termine aus", required=False))


def _specs():
    from app.plugins.registry import plugin_registry

    specs = {s.key.upper(): s for p in plugin_registry.all() for s in p.settings}
    specs.update({s.key: s for s in _core_settings()})
    return specs


def _apply(key: str, value: str) -> None:
    attr = key.lower()
    if hasattr(settings, attr):
        try:
            setattr(settings, attr, value)
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("override %s nicht anwendbar: %s", key, exc)
    _extra[key.upper()] = value


def apply_overrides(db: Session) -> None:
    """Wendet gespeicherte Overrides beim Start an."""
    try:
        rows = db.query(ConfigOverride).all()
    except Exception as exc:  # noqa: BLE001  (Tabelle fehlt bei sehr altem Stand)
        logger.warning("config_overrides nicht lesbar: %s", exc)
        return
    for row in rows:
        _apply(row.key, decrypt(row.value) if row.secret else row.value)


def save_overrides(db: Session, values: Dict[str, str]) -> None:
    """Speichert bekannte Plugin-Einstellungen und wendet sie sofort an.

    Unbekannte Schlüssel werden ignoriert; geheime Felder mit leerem Wert bleiben unverändert.
    """
    specs = _specs()
    for key, raw in (values or {}).items():
        spec = specs.get(key.upper())
        if spec is None:
            continue
        value = (raw or "").strip()
        if spec.secret and not value:
            continue
        row = db.get(ConfigOverride, spec.key.upper()) or ConfigOverride(key=spec.key.upper())
        row.value = encrypt(value) if spec.secret else value
        row.secret = spec.secret
        db.add(row)
        _apply(spec.key, value)
    db.commit()


def set_plugin_enabled(db: Session, plugin_id: str, enabled: bool) -> None:
    """Schaltet ein Plugin an/aus (Override für PLUGINS_DISABLED, wirkt sofort)."""
    current = [p for p in settings.disabled_plugins if p != plugin_id]
    if not enabled:
        current.append(plugin_id)
    value = ",".join(current)
    row = db.get(ConfigOverride, "PLUGINS_DISABLED") or ConfigOverride(key="PLUGINS_DISABLED")
    row.value, row.secret = value, False
    db.add(row)
    db.commit()
    _apply("PLUGINS_DISABLED", value)


def disable_plugins(db: Session, plugin_ids: List[str]) -> None:
    """Switches several plugins off in one write (same override as :func:`set_plugin_enabled`)."""
    current = list(settings.disabled_plugins)
    current.extend(p for p in plugin_ids if p not in current)
    value = ",".join(current)
    row = db.get(ConfigOverride, "PLUGINS_DISABLED") or ConfigOverride(key="PLUGINS_DISABLED")
    row.value, row.secret = value, False
    db.add(row)
    db.commit()
    _apply("PLUGINS_DISABLED", value)
