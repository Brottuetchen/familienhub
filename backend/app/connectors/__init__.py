"""Connector-Layer – Hermes' intelligente Schicht über den Fachsystemen."""

from app.connectors.registry import get_registry, registry

__all__ = ["registry", "get_registry"]
