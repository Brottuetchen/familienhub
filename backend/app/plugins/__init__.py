"""Plugins: jede Integration (Nextcloud, Home Assistant, Shelfarr …) ist ein Plugin.

Eigene Plugins: Python-Paket mit Entry-Point in der Gruppe ``familienhub.plugins``,
der auf eine Plugin-Instanz oder -Klasse zeigt. Siehe ``docs/PLUGINS.md``.
"""

from app.plugins.base import CAPABILITIES, Plugin, Setting, get_setting  # noqa: F401
