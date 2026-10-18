"""Publishing to ntfy (https://docs.ntfy.sh/publish/#publish-as-json)."""

from __future__ import annotations

import json
from typing import Optional

import httpx

from app.core.logging_config import get_logger
from app.plugins.base import get_setting

logger = get_logger("service.ntfy")

# Labels of the reminder buttons; ntfy shows at most three actions
REMINDER_ACTIONS = {"done": "Erledigt", "snooze_1h": "In 1 Std.", "tomorrow": "Morgen"}
PRIORITY = {"reminder": 4, "house": 4, "task_due": 4}
TAGS = {"reminder": "alarm_clock", "house": "house", "shopping": "shopping_cart", "task_assigned": "white_check_mark",
        "task_due": "hourglass", "media": "clapper", "documents": "page_facing_up", "system": "gear"}


def ntfy_server() -> Optional[str]:
    """Server address when the plugin is active, else None."""
    from app.plugins.registry import plugin_registry

    plugin = plugin_registry.get("ntfy")
    if not plugin or not plugin.active:
        return None
    return str(get_setting("NTFY_URL")).rstrip("/")


def _public_url() -> Optional[str]:
    url = get_setting("HUB_PUBLIC_URL")
    return str(url).rstrip("/") if url else None


def build_message(topic: str, title: str, body: str, data: dict, category: str) -> dict:
    msg = {"topic": topic, "title": title, "message": body or title, "priority": PRIORITY.get(category, 3)}
    if category in TAGS:
        msg["tags"] = [TAGS[category]]
    hub = _public_url()
    if hub:
        msg["click"] = f"{hub}/"
        token, rid = data.get("action_token"), data.get("reminder_id")
        wanted = [a for a in str(data.get("actions") or "").split(",") if a in REMINDER_ACTIONS][:3]
        if token and rid and wanted:
            msg["actions"] = [{
                "action": "http", "label": REMINDER_ACTIONS[a], "url": f"{hub}/api/reminders/{rid}/action",
                "method": "POST", "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"action": a, "token": token}), "clear": True,
            } for a in wanted]
    return msg


async def publish(topic: str, title: str, body: str, data: dict, category: str) -> bool:
    server = ntfy_server()
    if not server:
        return False
    headers = {}
    token = get_setting("NTFY_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{server}/", json=build_message(topic, title, body, data or {}, category), headers=headers)
        if resp.status_code == 200:
            return True
        # Never log the token or the topic (the topic is the secret)
        logger.warning("ntfy publish failed: HTTP %d", resp.status_code)
    except httpx.HTTPError as exc:
        logger.warning("ntfy publish failed (%s)", type(exc).__name__)
    return False
