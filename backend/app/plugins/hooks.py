"""Calling plugin extension points safely, and sanitising what they return.

A plugin is third-party code. Every hook runs only for an *active* plugin (all required settings set, not
switched off), with a timeout, and every exception is caught and logged: a broken plugin never breaks a hub
screen. What a plugin returns is data from outside, so it is validated and truncated here before it reaches
a person (``docs/plugins.md``, "Extension points").
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.core.logging_config import get_logger
from app.plugins.base import Plugin

logger = get_logger("plugins.hooks")

# Seconds a hook may take before the hub gives up on it
TODAY_CARDS_TIMEOUT = 4.0
SCHEDULED_TIMEOUT = 120.0
REWARD_ACTION_TIMEOUT = 20.0
TEST_SETTINGS_TIMEOUT = 15.0

# --- "Today" cards ---

# Material icon names a card may use (the app maps each of them to the icon of the same name)
CARD_ICONS = (
    "extension", "info", "event", "schedule", "check_circle", "shopping_cart", "restaurant", "home", "school",
    "sports_soccer", "local_shipping", "cloud", "wb_sunny", "notifications", "favorite", "star", "book", "movie",
    "music_note", "directions_car", "directions_bus", "pets", "build", "eco", "water_drop", "bolt", "lock",
    "payments", "medication", "cake", "child_care", "fitness_center", "local_laundry_service", "delete_outline",
    "wifi", "thermostat", "photo", "celebration", "sync", "warning",
)
DEFAULT_ICON = "extension"
MAX_CARDS_PER_PLUGIN = 5
MAX_LINES = 6
MAX_TITLE, MAX_LINE, MAX_BADGE, MAX_LINK, MAX_IMAGE = 60, 160, 16, 500, 300
CARD_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
PLUGIN_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
PLUGIN_CARD_PREFIX = "plugin:"


def _clean(value: Any, limit: int) -> Optional[str]:
    """A single-line string of at most ``limit`` characters, or None if there is nothing left."""
    if not isinstance(value, str):
        return None
    # Line breaks and tabs become spaces (so words do not merge), other control characters vanish
    text = " ".join("".join(c if c >= " " and c != "\x7f" else " " if c in "\r\n\t" else "" for c in value).split())
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def valid_image(plugin_id: str, value: Any) -> Optional[str]:
    """A hub-relative path below ``/api/plugins/<id>/``, which the plugin's own authenticated router serves."""
    if not isinstance(value, str) or len(value) > MAX_IMAGE:
        return None
    prefix = f"/api/plugins/{plugin_id}/"
    low = value.lower()
    if (not value.startswith(prefix) or len(value) == len(prefix) or "//" in value[1:] or "\\" in value
            or ".." in value or "%2e" in low or "%2f" in low or "%5c" in low or any(c <= " " for c in value)):
        return None
    return value


def valid_link(value: Any) -> Optional[str]:
    if not isinstance(value, str) or len(value) > MAX_LINK:
        return None
    return value if re.match(r"^https://[^\s/?#@]+(/\S*)?$", value) else None


def sanitize_card(plugin: Plugin, raw: Any) -> Optional[Dict[str, Any]]:
    """The card as the app gets it, or None if it is unusable (no id or nothing to show). Invalid optional
    fields are dropped, the card stays."""
    if not isinstance(raw, dict):
        return None
    card_id = raw.get("id")
    title = _clean(raw.get("title"), MAX_TITLE)
    if not isinstance(card_id, str) or not CARD_ID_RE.match(card_id) or title is None:
        return None
    lines: List[Dict[str, Any]] = []
    for line in raw.get("lines") if isinstance(raw.get("lines"), list) else []:
        text = _clean(line.get("text"), MAX_LINE) if isinstance(line, dict) else _clean(line, MAX_LINE)
        if text is None:
            continue
        secondary = _clean(line.get("secondary"), MAX_LINE) if isinstance(line, dict) else None
        lines.append({"text": text, "secondary": secondary})
        if len(lines) >= MAX_LINES:
            break
    icon = raw.get("icon")
    return {
        "key": f"{PLUGIN_CARD_PREFIX}{plugin.id}:{card_id}",
        "plugin": plugin.id,
        "plugin_name": _clean(plugin.name, MAX_TITLE) or plugin.id,
        "id": card_id,
        "title": title,
        "icon": icon if icon in CARD_ICONS else DEFAULT_ICON,
        "lines": lines,
        "image": valid_image(plugin.id, raw.get("image")),
        "link": valid_link(raw.get("link")),
        "badge": _clean(raw.get("badge"), MAX_BADGE),
    }


def sanitize_cards(plugin: Plugin, raw: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for item in raw if isinstance(raw, list) else []:
        card = sanitize_card(plugin, item)
        if card is None or card["id"] in seen:
            continue
        seen.add(card["id"])
        out.append(card)
        if len(out) >= MAX_CARDS_PER_PLUGIN:
            break
    return out


async def _today_cards_of(plugin: Plugin, user, db) -> List[Dict[str, Any]]:
    try:
        raw = await asyncio.wait_for(plugin.today_cards(user, db), TODAY_CARDS_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning("Plugin %s: today_cards took longer than %ss", plugin.id, TODAY_CARDS_TIMEOUT)
        return []
    except Exception as exc:  # noqa: BLE001 - a plugin must never break "Today"
        logger.warning("Plugin %s: today_cards failed: %s", plugin.id, type(exc).__name__)
        return []
    return sanitize_cards(plugin, raw)


async def collect_today_cards(user, db) -> List[Dict[str, Any]]:
    """Cards of all active plugins for this person, in plugin order; one slow plugin does not delay the others."""
    from app.plugins.registry import plugin_registry

    active = [p for p in plugin_registry.all()
              if p.active and type(p).today_cards is not Plugin.today_cards]
    if not active:
        return []
    results = await asyncio.gather(*(_today_cards_of(p, user, db) for p in active))
    return [card for cards in results for card in cards]


def is_plugin_card_id_format(card_id: Any) -> bool:
    """``plugin:<plugin id>:<card id>`` with valid parts, whether or not the plugin is active."""
    if not isinstance(card_id, str) or not card_id.startswith(PLUGIN_CARD_PREFIX):
        return False
    parts = card_id.split(":")
    return len(parts) == 3 and bool(PLUGIN_ID_RE.match(parts[1])) and bool(CARD_ID_RE.match(parts[2]))


def is_plugin_card_id(card_id: Any) -> bool:
    """``plugin:<plugin id>:<card id>`` of an active plugin (what a saved Today layout may contain)."""
    if not is_plugin_card_id_format(card_id):
        return False
    parts = card_id.split(":")
    from app.plugins.registry import plugin_registry

    plugin = plugin_registry.get(parts[1])
    return bool(plugin is not None and plugin.active)


# --- Result of a "Test connection" ---

def _result(value: Any, fallback: str) -> Dict[str, Any]:
    """``{"ok", "level", "message"}`` from whatever a plugin returned."""
    if not isinstance(value, dict):
        return {"ok": False, "level": "error", "message": fallback}
    ok = value.get("ok") is True
    level = value.get("level")
    if level not in ("ok", "info", "warn", "error"):
        level = "ok" if ok else "error"
    message = _clean(value.get("message"), 300) or ("OK" if ok else fallback)
    return {"ok": ok, "level": level, "message": message}


def sanitize_result(value: Any, fallback: str = "Action failed") -> Dict[str, Any]:
    return _result(value, fallback)


async def run_test_settings(plugin: Plugin, values: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """The plugin's own connection test with ``values``; None if it has none. Never raises."""
    if not plugin.has_test:
        return None
    try:
        raw = await asyncio.wait_for(plugin.test_settings(dict(values)), TEST_SETTINGS_TIMEOUT)
    except asyncio.TimeoutError:
        return {"ok": False, "level": "error", "message": "Zeitüberschreitung – Adresse und Netzwerk prüfen"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Plugin %s: test_settings failed: %s", plugin.id, type(exc).__name__)
        return {"ok": False, "level": "error", "message": "Der Test des Plugins ist fehlgeschlagen"}
    if raw is None:
        return None
    return _result(raw, "Der Test des Plugins ist fehlgeschlagen")


async def call_safely(plugin: Plugin, name: str, make: Callable[[], Awaitable[Any]], timeout: float) -> Any:
    """``await make()`` with a timeout; exceptions are logged and raise nothing (returns None on failure)."""
    try:
        return await asyncio.wait_for(make(), timeout)
    except asyncio.TimeoutError:
        logger.warning("Plugin %s: %s took longer than %ss", plugin.id, name, timeout)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Plugin %s: %s failed: %s", plugin.id, name, type(exc).__name__)
    return None
