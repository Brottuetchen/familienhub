"""Smart-Home-Connector für Home Assistant (https://www.home-assistant.io).

Steuerung von Licht, Heizung, Kameras, Türen und Sensoren sowie eine
verdichtete Übersicht für das Dashboard ("Familienstatus", Energie, offene Türen).
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, List, Optional

from app.config import settings
from app.connectors.base import BaseConnector, ConnectorError


def house_entities(value: str) -> list[str]:
    """Geordnete Auswahl; keine Pfade/URLs und höchstens sechs verschiedene IDs."""
    entities = list(dict.fromkeys(e.strip() for e in value.split(",") if e.strip()))
    if len(entities) > 6 or any(not re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+", e) for e in entities):
        raise ValueError("Haus-Karte: höchstens 6 gültige Entitäts-IDs, kommagetrennt")
    return entities


def house_write_entities(value: str) -> list[str]:
    entities = house_entities(value)
    if any(e.split(".")[0] not in {"light", "switch", "script", "scene"} for e in entities):
        raise ValueError("Haussteuerung: nur light, switch, script und scene erlaubt")
    return entities


class HomeAssistantConnector(BaseConnector):
    name = "homeassistant"
    display_name = "Smart Home (Home Assistant)"
    category = "smarthome"
    icon = "🏠"

    @property
    def is_configured(self) -> bool:
        return bool(settings.homeassistant_url and settings.homeassistant_token)

    @property
    def base_url(self) -> Optional[str]:
        return settings.homeassistant_url

    def _auth_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.homeassistant_token}",
            "Content-Type": "application/json",
        }

    async def _probe(self) -> bool:
        data = await self._get_json("/api/")
        return isinstance(data, dict)

    async def get_states(self, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """Alle Entitäts-Zustände (optional nach Domain gefiltert)."""
        if not self.is_configured:
            return []
        try:
            states = await self._get_json("/api/states")
            if not isinstance(states, list):
                return []
            if domain:
                states = [s for s in states if str(s.get("entity_id", "")).startswith(f"{domain}.")]
            return [
                {
                    "entity_id": s.get("entity_id"),
                    "state": s.get("state"),
                    "name": (s.get("attributes") or {}).get("friendly_name", s.get("entity_id")),
                    "attributes": s.get("attributes", {}),
                }
                for s in states
            ]
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("homeassistant get_states failed: %s", exc)
            return []

    async def get_house_states(self) -> Dict[str, Any]:
        """Nur die für die Familie ausgewählten Zustände, ohne weitere Attribute."""
        if not self.is_configured or "homeassistant" in settings.disabled_plugins:
            return {"status": "not_configured", "error": None, "items": []}
        try:
            entities = house_entities(settings.ha_house_entities)
            if not entities:
                return {"status": "not_configured", "error": None, "items": []}
            # ponytail: Momentaufnahme beim Heute-Abruf; WebSocket erst bei Bedarf an Live-Updates.
            raw = await self._get_json("/api/states")
            if not isinstance(raw, list) or any(
                not isinstance(s, dict) or not isinstance(s.get("entity_id"), str) for s in raw
            ):
                raise ValueError("Ungültige HA-Zustandsliste")
            states = {s["entity_id"]: s for s in raw}
            items = []
            for entity in entities:
                state = states.get(entity, {})
                attrs = state.get("attributes") or {}
                if not isinstance(attrs, dict):
                    raise ValueError("Ungültige HA-Zustandsattribute")
                value = state.get("state")
                if not isinstance(value, str) or value in ("unknown", "unavailable"):
                    value = None
                name, unit = attrs.get("friendly_name"), attrs.get("unit_of_measurement")
                items.append({"entity_id": entity, "name": name if isinstance(name, str) and name else entity,
                              "state": value, "unit": unit if isinstance(unit, str) else None})
            missing = any(item["state"] is None for item in items)
            return {"status": "unavailable" if missing else "ok",
                    "error": "Einige Haus-Zustände sind nicht verfügbar" if missing else None, "items": items}
        except Exception:
            self.logger.warning("Haus-Zustände nicht abrufbar", exc_info=True)
            return {"status": "unavailable", "error": "Haus-Zustände gerade nicht verfügbar", "items": []}

    def _house_selection(self) -> list[str]:
        if not self.is_configured or "homeassistant" in settings.disabled_plugins:
            raise ConnectorError("Haussteuerung nicht konfiguriert")
        return house_write_entities(settings.ha_house_write_entities)

    @staticmethod
    def _house_control(entity: str, raw: Any, can_write: bool) -> Dict[str, Any]:
        if not isinstance(raw, dict) or raw.get("entity_id") != entity:
            raise ValueError("Ungültiger HA-Zustand")
        attrs = raw.get("attributes") or {}
        if not isinstance(attrs, dict):
            raise ValueError("Ungültige HA-Attribute")
        domain = entity.split(".")[0]
        state = raw.get("state")
        if (not isinstance(state, str) or not state or state in {"unknown", "unavailable"}
                or (domain in {"light", "switch", "script"} and state not in {"on", "off"})):
            state = None
        actions = []
        modes = attrs.get("supported_color_modes")
        dimmable = domain == "light" and isinstance(modes, list) and any(
            m in {"brightness", "color_temp", "hs", "xy", "rgb", "rgbw", "rgbww", "white"}
            for m in modes if isinstance(m, str)
        )
        if state is not None and can_write:
            actions = ["turn_on", "turn_off"] if domain in {"light", "switch"} else ["activate"]
            if dimmable:
                actions.append("brightness")
        brightness = attrs.get("brightness")
        name = attrs.get("friendly_name")
        return {"entity_id": entity, "name": name if isinstance(name, str) and name else entity,
                "state": state, "actions": actions,
                "brightness": brightness if dimmable and type(brightness) is int and 0 <= brightness <= 255 else None}

    async def get_house_controls(self, can_write: bool) -> Dict[str, Any]:
        try:
            entities = self._house_selection()
        except ConnectorError:
            return {"status": "not_configured", "error": None, "items": []}
        except ValueError:
            self.logger.warning("Ungültige Haussteuerungs-Auswahl", exc_info=True)
            return {"status": "unavailable", "error": "Haussteuerung nicht verfügbar", "items": []}
        if not entities:
            return {"status": "not_configured", "error": None, "items": []}

        async def load(entity):
            try:
                return self._house_control(entity, await self._get_json(f"/api/states/{entity}"), can_write)
            except Exception:
                self.logger.warning("Haussteuerungs-Zustand nicht abrufbar", exc_info=True)
                return {"entity_id": entity, "name": entity, "state": None, "actions": [], "brightness": None}

        items = await asyncio.gather(*(load(entity) for entity in entities))
        missing = any(item["state"] is None for item in items)
        return {"status": "unavailable" if missing else "ok",
                "error": "Einige Haus-Zustände sind nicht verfügbar" if missing else None, "items": items}

    async def house_action(self, entity_id: str, action: str, brightness: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Führt die Aktion genau einmal aus. Gibt den neuen Zustand zurück, wenn HA ihn mitliefert, sonst None."""
        if entity_id not in self._house_selection():
            raise ValueError("Entität nicht zum Schreiben freigegeben")
        domain = entity_id.split(".")[0]
        allowed = {"turn_on", "turn_off", "brightness"} if domain == "light" else (
            {"turn_on", "turn_off"} if domain == "switch" else {"activate"})
        if action not in allowed:
            raise ValueError("Aktion nicht unterstützt")
        configuration = (self.base_url, settings.homeassistant_token)
        try:
            control = self._house_control(entity_id, await self._get_json(f"/api/states/{entity_id}"), True)
        except Exception as exc:
            self.logger.warning("Hausaktion: Zustand nicht prüfbar", exc_info=True)
            raise ConnectorError("Haus-Zustand nicht verfügbar; Aktion nicht gesendet") from exc
        if control["state"] is None:
            raise ConnectorError("Haus-Zustand nicht verfügbar; Aktion nicht gesendet")
        if action not in control["actions"]:
            raise ValueError("Aktion vom Gerät nicht unterstützt")
        # Laufzeitentzug auch während der vorgeschalteten Zustandsabfrage beachten.
        if entity_id not in self._house_selection() or configuration != (self.base_url, settings.homeassistant_token):
            raise ConnectorError("Haus-Konfiguration geändert; Aktion nicht gesendet")
        service = "turn_on" if action in {"activate", "brightness"} else action
        body: Dict[str, Any] = {"entity_id": entity_id}
        if action == "brightness":
            body["brightness"] = brightness
        try:
            async with self._client() as client:
                response = await client.post(f"/api/services/{domain}/{service}", json=body, follow_redirects=False)
                response.raise_for_status()
        except Exception as exc:
            self.logger.warning("Hausaktion fehlgeschlagen; keine Wiederholung", exc_info=True)
            raise ConnectorError("Aktion nicht bestätigt; Zustand aktualisieren. Nicht automatisch erneut ausführen.") from exc
        # HA antwortet mit den Zuständen, die sich während des Aufrufs geändert haben.
        try:
            changed = response.json()
        except ValueError:
            return None
        if not isinstance(changed, list):
            return None
        for item in changed:
            if isinstance(item, dict) and item.get("entity_id") == entity_id:
                control = self._house_control(entity_id, item, True)
                return control if control["state"] is not None else None
        return None

    async def get_overview(self) -> Dict[str, Any]:
        """Verdichtete Smart-Home-Übersicht fürs Dashboard."""
        if not self.is_configured:
            return {}
        states = await self.get_states()
        lights_on = [s for s in states if s["entity_id"].startswith("light.") and s["state"] == "on"]
        doors_open = [
            s
            for s in states
            if s["entity_id"].startswith("binary_sensor.")
            and (s["attributes"].get("device_class") in {"door", "window"})
            and s["state"] == "on"
        ]
        temps = [
            s
            for s in states
            if s["entity_id"].startswith("sensor.")
            and s["attributes"].get("device_class") == "temperature"
        ]
        return {
            "lights_on": len(lights_on),
            "doors_windows_open": len(doors_open),
            "open_entities": [d["name"] for d in doors_open],
            "temperature_sensors": [
                {"name": t["name"], "value": t["state"], "unit": t["attributes"].get("unit_of_measurement")}
                for t in temps[:5]
            ],
        }

    async def call_service(self, domain: str, service: str, entity_id: str) -> bool:
        """Ruft einen HA-Service auf (z.B. light.turn_on)."""
        if not self.is_configured:
            return False
        try:
            async with self._client() as client:
                resp = await client.post(
                    f"/api/services/{domain}/{service}", json={"entity_id": entity_id}
                )
                resp.raise_for_status()
                return True
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("homeassistant call_service failed: %s", exc)
            return False

    async def get_todo_items(self, entity_id: str, status: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Liest Items einer Todo-Liste (HA liefert ohne status nur offene)."""
        if not self.is_configured:
            return []
        try:
            async with self._client() as client:
                resp = await client.post(
                    "/api/services/todo/get_items",
                    json={"entity_id": entity_id, **({"status": status} if status else {})},
                    params={"return_response": "true"},
                )
                resp.raise_for_status()
                data = resp.json()
                # Korrektes Feld ist service_response, nicht response
                return data.get("service_response", {}).get(entity_id, {}).get("items", [])
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("get_todo_items failed for %s: %s", entity_id, exc)
            raise  # Re-raise für Fehlerbehandlung im Router

    async def add_todo_item(self, entity_id: str, item: str) -> bool:
        """Fügt ein Item hinzu."""
        if not self.is_configured:
            return False
        try:
            async with self._client() as client:
                resp = await client.post(
                    "/api/services/todo/add_item", json={"entity_id": entity_id, "item": item}
                )
                resp.raise_for_status()
                return True
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("add_todo_item failed: %s", exc)
            return False

    async def update_todo_item(self, entity_id: str, item: str, status: str) -> bool:
        """Aktualisiert Item-Status (needs_action/completed)."""
        if not self.is_configured:
            return False
        try:
            async with self._client() as client:
                resp = await client.post(
                    "/api/services/todo/update_item",
                    json={"entity_id": entity_id, "item": item, "status": status},
                )
                resp.raise_for_status()
                return True
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("update_todo_item failed: %s", exc)
            return False

    async def remove_todo_item(self, entity_id: str, item: list[str] | str) -> bool:
        """Entfernt ein oder mehrere Items."""
        if not self.is_configured:
            return False
        # API erwartet eine Liste
        if isinstance(item, str):
            item = [item]
        try:
            async with self._client() as client:
                resp = await client.post(
                    "/api/services/todo/remove_item", json={"entity_id": entity_id, "item": item}
                )
                resp.raise_for_status()
                return True
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("remove_todo_item failed: %s", exc)
            return False

    async def get_calendar_events(self, entity_id: str, start: str, end: str) -> List[Dict[str, Any]]:
        """Liest Kalendereinträge."""
        if not self.is_configured:
            return []
        try:
            async with self._client() as client:
                resp = await client.get(
                    f"/api/calendars/{entity_id}", params={"start": start, "end": end}
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("get_calendar_events failed: %s", exc)
            return []
