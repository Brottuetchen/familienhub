"""Grundbausteine für Plugins."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

# Fähigkeiten, die die App kennt. Ein Bereich erscheint, sobald ein aktives Plugin ihn liefert.
CAPABILITIES = {
    "tasks": "Aufgaben",
    "calendar": "Termine",
    "shopping": "Einkauf",
    "meal_source": "Essensplan-Quelle (zusätzlich zum eigenen Plan)",
    "meal_planning": "Rezepte suchen und einplanen",
    "documents": "Dokumente (Paperless)",
    "books": "Bücher & Hörbücher",
    "media_requests": "Filme & Serien wünschen",
    "weather": "Wetter in „Heute“",
    "push_ntfy": "Push über ntfy",
}


def get_setting(key: str, default: Any = None) -> Any:
    """Wert einer Einstellung: Admin-Override > Kern-Settings > Umgebung."""
    from app.config import settings
    from app.services.config_store import get_override

    override = get_override(key)
    if override not in (None, ""):
        return override
    attr = key.lower()
    if hasattr(settings, attr):
        value = getattr(settings, attr)
        if value not in (None, ""):
            return value
    return os.environ.get(key.upper(), default)


@dataclass(frozen=True)
class Setting:
    """Eine Einstellung, die ein Plugin braucht (für Doku und Einrichtungs-Assistent)."""

    key: str  # Umgebungsvariable, z. B. HOMEASSISTANT_URL
    label: str
    secret: bool = False
    required: bool = True
    help: str = ""


@dataclass
class Plugin:
    """Basisklasse. Unterklassen setzen die Felder und überschreiben bei Bedarf Methoden."""

    id: str
    name: str
    version: str = "1.0.0"
    description: str = ""
    capabilities: frozenset = field(default_factory=frozenset)
    settings: tuple = ()
    builtin: bool = False
    # Hub's own source of an area (tasks, shopping, calendar): used when no other plugin provides it
    fallback: bool = False
    # Tasks only: this source can hold the shared family list and household rotation
    family_tasks: bool = False

    def routers(self) -> List[APIRouter]:
        """FastAPI-Router des Plugins (werden beim Start eingebunden)."""
        return []

    def task_connector(self, user_id: int, db) -> Any:
        """Persönlicher Aufgabenadapter; Plugins ohne Aufgaben liefern keinen."""
        return None

    def is_configured(self) -> bool:
        """Standard: alle Pflicht-Einstellungen haben einen Wert."""
        return all(get_setting(s.key) not in (None, "") for s in self.settings if s.required)

    def is_set_up(self) -> bool:
        """Set up by the admin, not only usable through built-in defaults. Plugins that work without any
        settings (weather, CalDAV with accounts per person) override this, so the setup wizard does not show
        them as set up and preselected."""
        return self.is_configured()

    def health_url(self) -> Optional[str]:
        """Adresse für die Erreichbarkeitsprüfung in der Verwaltung; Standard: erste gesetzte *_URL."""
        for s in self.settings:
            if s.key.endswith("_URL") and not s.key.endswith("PUBLIC_URL"):
                value = get_setting(s.key)
                if value:
                    return str(value)
        return None

    async def check(self) -> Optional[Dict[str, Any]]:
        """Own status for the admin overview (``{"status", "message"}``) when there is no address to probe."""
        return None

    def missing_settings(self) -> List[str]:
        return [s.key for s in self.settings if s.required and get_setting(s.key) in (None, "")]

    def describe(self) -> Dict[str, Any]:
        from app.config import settings as core

        disabled = self.id in core.disabled_plugins
        configured = self.is_configured()
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "builtin": self.builtin,
            "fallback": self.fallback,
            "capabilities": sorted(self.capabilities),
            "configured": configured,
            "set_up": self.is_set_up(),
            "disabled": disabled,
            "active": configured and not disabled,
            "missing_settings": self.missing_settings(),
            "settings": [
                {"key": s.key, "label": s.label, "secret": s.secret, "required": s.required, "help": s.help}
                for s in self.settings
            ],
        }

    @property
    def active(self) -> bool:
        from app.config import settings as core

        return self.is_configured() and self.id not in core.disabled_plugins


def as_plugin(obj: Any) -> Optional[Plugin]:
    """Entry-Point-Ziel (Instanz, Klasse oder Fabrik) → Plugin-Instanz."""
    if isinstance(obj, Plugin):
        return obj
    if callable(obj):
        made = obj()
        return made if isinstance(made, Plugin) else None
    return None
