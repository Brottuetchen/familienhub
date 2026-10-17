"""Feature-Flags für Module und Connectors.

Nicht konfigurierte oder ausgeschaltete Module erscheinen nicht in API-Übersichten,
Dashboard, Navigation oder KI-Werkzeugen.
"""

from __future__ import annotations

from app.config import get_settings


class FeatureFlags:
    """Zentrale Prüfung, ob ein Modul aktiv ist."""

    @staticmethod
    def media() -> bool:
        """Medien: Sonarr, Radarr, Overseerr, Audiobookshelf, TeddyCloud."""
        return get_settings().feature_media

    @staticmethod
    def finance() -> bool:
        """Finanzen."""
        return get_settings().feature_finance

    @staticmethod
    def packages() -> bool:
        """Paket-Tracking."""
        return get_settings().feature_packages

    @staticmethod
    def inventory() -> bool:
        """Inventar (Homebox)."""
        return get_settings().feature_inventory

    @staticmethod
    def documents() -> bool:
        """Dokumente (Paperless)."""
        return get_settings().feature_documents

    @staticmethod
    def kitchenowl() -> bool:
        """Einkauf über KitchenOwl."""
        return get_settings().feature_kitchenowl

    @staticmethod
    def vikunja() -> bool:
        """Aufgaben über Vikunja."""
        return get_settings().feature_vikunja


features = FeatureFlags()
