"""Basis-Abstraktion für Connectors.

Ein Connector ist die Brücke zwischen Hermes und einem externen Fachsystem
(Nextcloud, Vikunja, KitchenOwl, Paperless, Home Assistant, ...). Hermes
speichert diese Daten NICHT doppelt, sondern liest/schreibt live über die API
des jeweiligen Systems.

Design-Prinzipien:
  * **Graceful Degradation** – ist ein Connector nicht konfiguriert, wirft er
    keinen Fehler, sondern meldet ``configured=False`` und liefert leere Daten.
  * **Fehlertoleranz** – API-Fehler werden geloggt und in ``ConnectorError``
    bzw. leere Ergebnisse übersetzt, damit das Dashboard nie komplett ausfällt.
  * **Einheitliche Datenformen** – Connectors liefern schlichte dicts/lists in
    dokumentierten Formen, die die Router direkt weiterreichen können.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from app.config import settings
from app.core.logging_config import get_logger


class ConnectorError(Exception):
    """Fehler bei der Kommunikation mit einem Fachsystem."""


class BaseConnector:
    """Gemeinsame Basisklasse aller Connectors."""

    #: Technischer, eindeutiger Name (z.B. "vikunja").
    name: str = "base"
    #: Anzeigename für die UI.
    display_name: str = "Base"
    #: Modul-Kategorie (calendar | tasks | shopping | documents | inventory | smarthome | media | weather).
    category: str = "misc"
    #: Emoji/Icon-Hinweis für die UI.
    icon: str = "🔌"

    def __init__(self) -> None:
        self.logger = get_logger(f"connector.{self.name}")

    # --- Konfiguration ---

    @property
    def is_configured(self) -> bool:
        """True, wenn genügend Konfiguration für Live-Betrieb vorliegt."""
        return False

    @property
    def base_url(self) -> Optional[str]:
        return None

    def _auth_headers(self) -> Dict[str, str]:
        return {}

    # --- HTTP-Helfer ---

    def _client(self, **kwargs: Any) -> httpx.AsyncClient:
        base = (self.base_url or "").rstrip("/")
        return httpx.AsyncClient(
            base_url=base,
            headers=self._auth_headers(),
            timeout=settings.connector_timeout,
            verify=settings.verify_tls,
            follow_redirects=True,
            **kwargs,
        )

    async def _get_json(self, path: str, **kwargs: Any) -> Any:
        async with self._client() as client:
            resp = await client.get(path, **kwargs)
            resp.raise_for_status()
            return resp.json()

    async def _post_json(self, path: str, json: Any, **kwargs: Any) -> Any:
        async with self._client() as client:
            resp = await client.post(path, json=json, **kwargs)
            resp.raise_for_status()
            return resp.json() if resp.content else None

    # --- Standardmethoden ---

    async def health(self) -> Dict[str, Any]:
        """Prüft die Erreichbarkeit des Fachsystems.

        Returns dict: ``{status, configured, detail}`` mit status in
        online | offline | disabled | error.
        """
        if not self.is_configured:
            return {"status": "disabled", "configured": False, "detail": "not configured"}
        try:
            ok = await self._probe()
            return {
                "status": "online" if ok else "error",
                "configured": True,
                "detail": None if ok else "probe failed",
            }
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("health check failed: %s", exc)
            return {"status": "offline", "configured": True, "detail": str(exc)}

    async def _probe(self) -> bool:
        """Konkrete Erreichbarkeitsprüfung – von Subklassen überschrieben."""
        if not self.base_url:
            return False
        async with self._client() as client:
            resp = await client.get("/")
            return resp.status_code < 500

    async def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Optionale globale Suche. Standard: keine Ergebnisse.

        Ergebnis-Form: ``{title, subtitle, url, source, category, icon}``.
        """
        return []

    def info(self) -> Dict[str, Any]:
        """Metadaten für die UI (Connector-Übersicht)."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "category": self.category,
            "icon": self.icon,
            "configured": self.is_configured,
        }
