"""Lädt eingebaute und installierte Plugins."""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Dict, List, Optional

from fastapi import FastAPI

from app.core.logging_config import get_logger
from app.plugins.base import Plugin, as_plugin

logger = get_logger("plugins")
ENTRY_POINT_GROUP = "familienhub.plugins"


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: Dict[str, Plugin] = {}

    def register(self, plugin: Plugin) -> None:
        if plugin.id in self._plugins:
            logger.warning("Plugin-ID doppelt, übersprungen: %s", plugin.id)
            return
        self._plugins[plugin.id] = plugin

    def load(self) -> None:
        from app.plugins.builtin import BUILTIN_PLUGINS

        for plugin in BUILTIN_PLUGINS:
            self.register(plugin)
        for ep in entry_points(group=ENTRY_POINT_GROUP):
            try:
                plugin = as_plugin(ep.load())
            except Exception as exc:  # noqa: BLE001 – ein kaputtes Plugin darf den Hub nicht stoppen
                logger.warning("Plugin %s nicht ladbar: %s", ep.name, exc)
                continue
            if plugin is None:
                logger.warning("Entry-Point %s liefert kein Plugin", ep.name)
                continue
            self.register(plugin)
            logger.info("Plugin geladen: %s %s", plugin.id, plugin.version)

    def all(self) -> List[Plugin]:
        return list(self._plugins.values())

    def get(self, plugin_id: str) -> Optional[Plugin]:
        return self._plugins.get(plugin_id)

    def provider(self, capability: str) -> Optional[Plugin]:
        """Source of an area: the admin's choice (``<CAPABILITY>_SOURCE``), else the first active plugin.

        Built-in plugins come before external ones; the hub's own sources (``fallback``) come last,
        so they only serve an area when nothing else does.
        """
        from app.plugins.base import get_setting

        choice = str(get_setting(f"{capability.upper()}_SOURCE") or "").strip()
        chosen = self._plugins.get(choice)
        if chosen and capability in chosen.capabilities and chosen.active:
            return chosen
        ordered = sorted(self._plugins.values(), key=lambda p: p.fallback)  # stable: keeps registration order
        for plugin in ordered:
            if capability in plugin.capabilities and plugin.active:
                return plugin
        return None

    def providers(self, capability: str) -> List[Plugin]:
        """Alle aktiven Anbieter; Aufgaben wählen niemals implizit den ersten."""
        return [p for p in self.all() if capability in p.capabilities and p.active]

    def task_connector(self, provider: str, user_id: int, db, account: str | None = None, *, implicit: bool = False):
        from fastapi import HTTPException

        plugin = self.get(provider)
        if not plugin or "tasks" not in plugin.capabilities or not plugin.active:
            raise HTTPException(409, "Aufgabenanbieter ist nicht aktiv")
        if account is None and provider != "nextcloud" and not implicit:
            raise HTTPException(422, "Bitte Anbieter und eigenes Aufgabenkonto ausdrücklich wählen")
        connector = plugin.task_connector(user_id, db)
        if connector is None:
            raise HTTPException(409, "Aufgabenanbieter besitzt keinen persönlichen Adapter")
        if account is not None and account != connector.account_ref:
            raise HTTPException(403, "Dieses Aufgabenkonto gehört nicht zur aktuellen Sitzung")
        return connector

    def include_routers(self, app: FastAPI) -> None:
        for plugin in self._plugins.values():
            for router in plugin.routers():
                app.include_router(router)


plugin_registry = PluginRegistry()
plugin_registry.load()
