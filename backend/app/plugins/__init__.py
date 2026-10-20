"""Plugins: jede Integration (Nextcloud, Home Assistant, Shelfarr …) ist ein Plugin.

Eigene Plugins: Python-Paket mit Entry-Point in der Gruppe ``familienhub.plugins``,
der auf eine Plugin-Instanz oder -Klasse zeigt. See ``docs/plugins.md``.
"""

from app.plugins.base import CAPABILITIES, Plugin, Setting, get_setting  # noqa: F401
from app.plugins.sources import ShoppingConnector  # noqa: F401, E402
