"""Grundbausteine für Plugins."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
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
    "timetable": "Stundenplan",
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

    # Scheduled jobs (see ``scheduled``): minutes between runs, at least 5. Deliberately not a dataclass field, so a
    # subclass may set it as a class attribute or in ``__init__`` after ``super().__init__``.
    schedule_minutes = None

    def routers(self) -> List[APIRouter]:
        """FastAPI-Router des Plugins (werden beim Start eingebunden)."""
        return []

    def task_connector(self, user_id: int, db) -> Any:
        """Persönlicher Aufgabenadapter; Plugins ohne Aufgaben liefern keinen."""
        return None

    async def calendar_events(self, start: datetime, end: datetime, user, db) -> List[Dict[str, Any]]:
        """Read-only events of a plugin with the ``calendar`` capability in ``[start, end)`` (local wall time).

        Each event is a dict shaped like the hub's ICS events: ``title``, ``start``, ``end`` (ISO date for all-day
        events, with an exclusive end; ISO date-time otherwise), ``all_day``, ``calendar`` (display name) and
        ``calendar_id`` (must start with ``"<plugin id>:"``), optionally ``location``, ``description`` and ``color``.
        The hub forces ``source`` to the plugin id and ``writable`` to false, and drops events with a foreign
        ``calendar_id``. Raising or taking longer than about 5 s only skips this plugin. Default: no events.
        """
        return []

    def calendars(self, user, db) -> List[Dict[str, Any]]:
        """The calendars this plugin offers, for the chips and filters: ``{"id": "<plugin id>:<x>", "name": …,
        "color": None | "#RRGGBB"}``. Default: none."""
        return []

    # --- Data sources (docs/plugins.md, "Data sources"). Every hook has a safe default; the hub calls them with
    # a timeout and catches every exception, so a failing plugin never breaks the app. ---

    def shopping_connector(self, db) -> Any:
        """Capability ``shopping``: the plugin's shopping list as a ``ShoppingConnector`` (``app.plugins.sources``),
        used when the admin chose this plugin under *Sources per area*. ``None`` = not supported."""
        return None

    async def recipe_search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Capability ``meal_planning``: search recipes, ``[{id, name, thumbnail, url, minutes}]``."""
        return []

    async def recipe(self, recipe_id: str) -> Dict[str, Any]:
        """Capability ``meal_planning``: one recipe, ``{id, name, image, url, servings, minutes, ingredients, steps}``."""
        return {}

    async def recipe_to_shopping(self, recipe_ids: List[str], user_id: Optional[int] = None) -> Optional[int]:
        """Optional: put the ingredients on the plugin's own list; return how many recipes went in.
        ``None`` (default) = not supported, the hub then puts the ingredients on its shopping list."""
        return None

    async def timetable(self, child: Any, start: Any, end: Any, db) -> List[Dict[str, Any]]:
        """Provide lessons of a hub child between two dates (inclusive):
        ``[{date, start "HH:MM", end, title, kind, location, status, note, teacher}]``. Default: nothing."""
        return []

    async def timetable_people(self) -> List[Dict[str, Any]]:
        """Optional: people of the plugin's system that a child can be mapped to, ``[{id, name}]``."""
        return []

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

    # --- Extension points (docs/plugins.md, "Extension points"). The defaults do nothing. The hub calls them only
    # for active plugins, with a timeout, and catches every exception.

    async def today_cards(self, user, db) -> List[Dict[str, Any]]:
        """Cards for the person's "Today" screen; the shape is described in ``app.plugins.hooks``."""
        return []

    async def scheduled(self, db) -> None:
        """Periodic job, every ``schedule_minutes`` minutes (at least 5) while the plugin is active."""
        return None

    def reward_actions(self) -> List[Dict[str, Any]]:
        """Actions a parent can attach to a reward: ``[{"id", "label", "params": [field specs]}]``."""
        return []

    async def run_reward_action(self, action_id: str, params: Dict[str, Any], child, reward, db) -> Dict[str, Any]:
        """Runs an action when a parent approves the reward. Returns ``{"ok": bool, "message": str}``."""
        return {"ok": False, "message": "Unknown action"}

    async def test_settings(self, values: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """"Test connection" with the not-yet-saved ``values`` (a secret left empty is filled with the stored one).

        Return ``{"ok": bool, "level": "ok" | "info" | "warn" | "error", "message": str}``. A plugin that does not
        override this has no test of its own.
        """
        return None

    @property
    def has_test(self) -> bool:
        return type(self).test_settings is not Plugin.test_settings

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
            "needs_setup": not configured and not disabled,
            "has_test": self.has_test,
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
