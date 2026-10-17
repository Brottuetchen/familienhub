"""Connector-Registry (Datenzugriff der eingebauten Plugins).

Zentrale Verwaltung aller Connectors: Instanziierung (Singletons), Lookup nach
Name/Kategorie, aggregierte Health-Checks und globale Suche.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from app.config import get_settings
from app.connectors.base import BaseConnector
from app.connectors.caldav_connector import CalDAVConnector
from app.connectors.homeassistant_connector import HomeAssistantConnector
from app.connectors.nextcloud_tasks_connector import NextcloudTasksConnector
from app.connectors.weather_connector import WeatherConnector

# Datenzugriff je Dienst. Ob ein Connector genutzt wird, entscheidet das zugehörige Plugin
# (abschaltbar über PLUGINS_DISABLED).
PLUGIN_BY_CONNECTOR: Dict[str, str] = {
    "caldav": "nextcloud",
    "nextcloud_tasks": "nextcloud",
    "homeassistant": "homeassistant",
    "weather": "weather",
}


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: Dict[str, BaseConnector] = {}
        for connector_cls in (
            WeatherConnector,
            CalDAVConnector,
            NextcloudTasksConnector,
            HomeAssistantConnector,
        ):
            instance = connector_cls()
            self._connectors[instance.name] = instance

    def _is_enabled(self, connector: BaseConnector) -> bool:
        """Aus, wenn das zugehörige Plugin per PLUGINS_DISABLED abgeschaltet ist."""
        plugin_id = PLUGIN_BY_CONNECTOR.get(connector.name)
        return plugin_id is None or plugin_id not in get_settings().disabled_plugins

    # --- Lookup ---

    def get(self, name: str) -> Optional[BaseConnector]:
        connector = self._connectors.get(name)
        if connector and self._is_enabled(connector):
            return connector
        return None

    def by_category(self, category: str) -> Optional[BaseConnector]:
        for c in self._connectors.values():
            if c.category == category and self._is_enabled(c):
                return c
        return None

    def all(self) -> List[BaseConnector]:
        return [c for c in self._connectors.values() if self._is_enabled(c)]

    # --- Aggregierte Operationen ---

    async def health_all(self) -> List[Dict[str, Any]]:
        """Parallele Health-Checks aller Connectors."""
        connectors = self.all()
        results = await asyncio.gather(*(c.health() for c in connectors), return_exceptions=True)
        out: List[Dict[str, Any]] = []
        for connector, res in zip(connectors, results):
            base = connector.info()
            if isinstance(res, Exception):
                base.update({"status": "error", "detail": str(res)})
            else:
                base.update(res)
            out.append(base)
        return out


# Singleton-Instanz
registry = ConnectorRegistry()


def get_registry() -> ConnectorRegistry:
    return registry
