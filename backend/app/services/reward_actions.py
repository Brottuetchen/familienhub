"""Reward actions (kids mode): what a plugin does when a parent approves a reward.

A plugin offers actions with ``Plugin.reward_actions()`` (id, label, parameter fields) and carries them out in
``Plugin.run_reward_action()``. A parent attaches one action to a reward (``star_rewards.action_*``) and fills in
its parameters. When a parent approves a request for that reward, the action runs *after* the approval is
committed: a failing, slow or missing plugin never reverts the approval, the outcome is reported to the parent.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.plugins.base import Plugin
from app.plugins.hooks import REWARD_ACTION_TIMEOUT, _clean, call_safely, sanitize_result

logger = get_logger("service.reward_actions")

PARAM_TYPES = ("text", "number", "bool", "select")
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,30}$")
ACTION_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
MAX_ACTIONS_PER_PLUGIN, MAX_PARAMS, MAX_OPTIONS = 20, 8, 20
MAX_PARAM_VALUE = 300


def _param_spec(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict) or not isinstance(raw.get("key"), str) or not KEY_RE.match(raw["key"]):
        return None
    kind = raw.get("type", "text")
    if kind not in PARAM_TYPES:
        return None
    options: List[Dict[str, str]] = []
    if kind == "select":
        for o in raw.get("options") if isinstance(raw.get("options"), list) else []:
            value = _clean(o.get("value") if isinstance(o, dict) else o, 100)
            label = _clean(o.get("label") if isinstance(o, dict) else o, 60)
            if value is not None:
                options.append({"value": value, "label": label or value})
        if not options:
            return None
    default = raw.get("default")
    default = None if default is None else _clean(str(default).lower() if isinstance(default, bool) else str(default),
                                                   MAX_PARAM_VALUE)
    return {"key": raw["key"], "label": _clean(raw.get("label"), 60) or raw["key"], "type": kind,
            "required": raw.get("required", True) is not False and kind != "bool",
            "default": default, "help": _clean(raw.get("help"), 200) or "", "options": options[:MAX_OPTIONS]}


def _action_spec(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not ACTION_ID_RE.match(raw["id"]):
        return None
    label = _clean(raw.get("label"), 80)
    if label is None:
        return None
    params, seen = [], set()
    for p in raw.get("params") if isinstance(raw.get("params"), list) else []:
        spec = _param_spec(p)
        if spec is not None and spec["key"] not in seen:
            seen.add(spec["key"])
            params.append(spec)
    return {"id": raw["id"], "label": label, "params": params[:MAX_PARAMS]}


def plugin_actions(plugin: Plugin) -> List[Dict[str, Any]]:
    """The sanitised actions of one plugin; a plugin that fails offers none."""
    if type(plugin).reward_actions is Plugin.reward_actions:
        return []
    try:
        raw = plugin.reward_actions()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Plugin %s: reward_actions failed: %s", plugin.id, type(exc).__name__)
        return []
    out, seen = [], set()
    for item in raw if isinstance(raw, list) else []:
        spec = _action_spec(item)
        if spec is not None and spec["id"] not in seen:
            seen.add(spec["id"])
            out.append(spec)
    return out[:MAX_ACTIONS_PER_PLUGIN]


def available() -> List[Dict[str, Any]]:
    """Actions of all active plugins, for the reward form."""
    from app.plugins.registry import plugin_registry

    out = []
    for plugin in plugin_registry.all():
        if not plugin.active:
            continue
        for spec in plugin_actions(plugin):
            out.append({"plugin": plugin.id, "plugin_name": plugin.name, **spec})
    return out


def find(plugin_id: str, action_id: str) -> Optional[Tuple[Plugin, Dict[str, Any]]]:
    """(plugin, action spec) if the plugin is active and offers the action."""
    from app.plugins.registry import plugin_registry

    plugin = plugin_registry.get(plugin_id)
    if plugin is None or not plugin.active:
        return None
    spec = next((a for a in plugin_actions(plugin) if a["id"] == action_id), None)
    return (plugin, spec) if spec else None


def clean_params(spec: Dict[str, Any], values: Any) -> Dict[str, str]:
    """The parameter values checked against the action's field specs. Raises 422 (German text) on a problem."""
    values = values if isinstance(values, dict) else {}
    fields = {p["key"]: p for p in spec["params"]}
    unknown = sorted(set(map(str, values)) - set(fields))
    if unknown:
        raise HTTPException(422, "Unbekannter Parameter der Aktion")
    out: Dict[str, str] = {}
    for key, field in fields.items():
        raw = values.get(key)
        if isinstance(raw, bool):
            raw = "true" if raw else "false"
        elif isinstance(raw, (int, float)):
            raw = str(raw)
        raw = raw.strip() if isinstance(raw, str) else ""
        if len(raw) > MAX_PARAM_VALUE or any(c in raw for c in "\r\n\x00"):
            raise HTTPException(422, "Ungültiger Wert für einen Parameter der Aktion")
        if not raw:
            raw = field["default"] or ("false" if field["type"] == "bool" else "")
        if not raw:
            if field["required"]:
                raise HTTPException(422, "Pflichtparameter der Aktion fehlt")
            continue
        if field["type"] == "number":
            try:
                float(raw)
            except ValueError:
                raise HTTPException(422, "Ungültiger Wert für einen Parameter der Aktion") from None
        elif field["type"] == "bool" and raw not in ("true", "false"):
            raise HTTPException(422, "Ungültiger Wert für einen Parameter der Aktion")
        elif field["type"] == "select" and raw not in {o["value"] for o in field["options"]}:
            raise HTTPException(422, "Ungültiger Wert für einen Parameter der Aktion")
        out[key] = raw
    return out


def checked(action: Dict[str, Any]) -> Dict[str, str]:
    """The three column values for an action chosen by a parent, or 422 if it cannot be used right now."""
    found = find(str(action.get("plugin", "")), str(action.get("action", "")))
    if found is None:
        raise HTTPException(422, "Diese Aktion ist nicht verfügbar (Plugin nicht aktiv?)")
    return {"action_plugin": str(action["plugin"]), "action_id": str(action["action"]),
            "action_params": json.dumps(clean_params(found[1], action.get("params")))}


def attach(reward, action: Optional[Dict[str, Any]]) -> None:
    """Sets (or with ``None`` clears) the action of a reward after checking it against the active plugins."""
    values = checked(action) if action else {"action_plugin": None, "action_id": None, "action_params": None}
    for name, value in values.items():
        setattr(reward, name, value)


def stored_params(reward) -> Dict[str, str]:
    try:
        data = json.loads(reward.action_params or "{}")
    except ValueError:
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def action_view(reward) -> Optional[Dict[str, Any]]:
    """What a parent sees on a reward: the chosen action, its parameters and whether it can run right now."""
    if not reward.action_plugin or not reward.action_id:
        return None
    found = find(reward.action_plugin, reward.action_id)
    return {"plugin": reward.action_plugin, "action": reward.action_id, "params": stored_params(reward),
            "label": found[1]["label"] if found else reward.action_id,
            "plugin_name": found[0].name if found else reward.action_plugin, "available": found is not None}


async def run_for_request(db: Session, req, approver) -> Optional[Dict[str, Any]]:
    """Runs the action of the approved request's reward. ``None`` if the reward has none. Never raises."""
    from app.models.stars import StarReward
    from app.models.user import User

    try:
        reward = db.get(StarReward, req.reward_id) if req.reward_id else None
        if reward is None or not reward.action_plugin or not reward.action_id:
            return None
        base = {"plugin": reward.action_plugin, "action": reward.action_id}
        found = find(reward.action_plugin, reward.action_id)
        if found is None:
            logger.warning("Reward %s: action %s/%s not available (plugin off or removed)", reward.id,
                           reward.action_plugin, reward.action_id)
            return {**base, "ok": False, "message": "Das Plugin der Belohnungs-Aktion ist nicht aktiv"}
        plugin, _ = found
        child = db.get(User, req.user_id)
        params = stored_params(reward)
        raw = await call_safely(plugin, f"reward action {reward.action_id}",
                                lambda: plugin.run_reward_action(reward.action_id, params, child, reward, db),
                                REWARD_ACTION_TIMEOUT)
        if raw is None:
            db.rollback()  # the plugin may have left a half-finished transaction behind
            logger.warning("Reward %s: action %s/%s failed or timed out", reward.id, plugin.id, reward.action_id)
            return {**base, "ok": False, "message": "Die Aktion ist fehlgeschlagen oder hat zu lange gedauert"}
        result = sanitize_result(raw)
        if not result["ok"]:
            logger.warning("Reward %s: action %s/%s reported failure", reward.id, plugin.id, reward.action_id)
        return {**base, "ok": result["ok"], "message": result["message"]}
    except Exception as exc:  # noqa: BLE001 - the approval stays, whatever happens here
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        logger.warning("Reward action failed: %s", type(exc).__name__)
        return {"plugin": "", "action": "", "ok": False, "message": "Die Aktion ist fehlgeschlagen"}
