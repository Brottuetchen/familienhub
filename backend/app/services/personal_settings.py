"""Settings a person fills in for a plugin (``Plugin.personal_settings``, manifest ``personal_settings``).

Stored in ``plugin_user_settings`` per plugin, person and key. Secrets are Fernet-encrypted like the admin's plugin
settings (``config_overrides``) and never leave the hub: the API only reports whether one is set. A value that is
not stored falls back to the declared default.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.crypto import decrypt, encrypt
from app.models.plugin_user_setting import PluginUserSetting
from app.plugins.base import Plugin, Setting
from app.plugins.manifest import check_value


def spec_of(plugin: Plugin, key: str) -> Optional[Setting]:
    return next((s for s in plugin.personal_settings if s.key == key), None)


def _rows(db: Session, plugin_id: str, user_id: int) -> Dict[str, PluginUserSetting]:
    rows = db.query(PluginUserSetting).filter(PluginUserSetting.plugin_id == plugin_id,
                                              PluginUserSetting.user_id == user_id).all()
    return {r.key: r for r in rows}


def _plain(row: PluginUserSetting) -> str:
    return decrypt(row.value) if row.secret else (row.value or "")


def values(db: Session, plugin: Plugin, user_id: int) -> Dict[str, str]:
    """Every declared key with its stored value (decrypted), else the default, else ``""``. For plugin code only."""
    rows = _rows(db, plugin.id, user_id)
    return {s.key: (_plain(rows[s.key]) if s.key in rows else (s.default or "")) for s in plugin.personal_settings}


def get_value(db: Session, plugin: Plugin, user_id: int, key: str) -> Optional[str]:
    """One declared setting of one person; ``None`` for an undeclared key or when nothing (also no default) is set."""
    spec = spec_of(plugin, key)
    if spec is None:
        return None
    row = db.get(PluginUserSetting, (plugin.id, user_id, key))
    value = _plain(row) if row is not None else (spec.default or "")
    return value or None


def form(db: Session, plugin: Plugin, user_id: int) -> List[Dict[str, Any]]:
    """The fields for the app: spec plus the person's value (empty for secrets) and ``is_set``."""
    rows = _rows(db, plugin.id, user_id)
    out = []
    for s in plugin.personal_settings:
        stored = _plain(rows[s.key]) if s.key in rows else ""
        shown = stored or ("" if s.secret else (s.default or ""))
        out.append({"key": s.key, "label": s.label, "help": s.help, "type": s.type, "secret": s.secret,
                    "required": s.required, "default": s.default, "example": s.example,
                    "value": "" if s.secret else shown, "is_set": bool(stored)})
    return out


def _coerce(raw: Any, key: str) -> str:
    if isinstance(raw, bool):
        return "true" if raw else "false"
    if isinstance(raw, (int, float)):
        return str(raw)
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise ValueError(f"Wert von {key} ist ungültig")
    return raw.strip()


def check(plugin: Plugin, given: Dict[str, Any]) -> Dict[str, str]:
    """Validated input: ``{key: value}`` for the declared keys the caller sent. Raises ``ValueError`` (German)."""
    known = {s.key: s for s in plugin.personal_settings}
    unknown = sorted(set(given or {}) - set(known))
    if unknown:
        raise ValueError(f"Unbekannte Einstellung: {', '.join(unknown)}")
    return {key: check_value(known[key].type, _coerce(raw, key), key) if _coerce(raw, key) else ""
            for key, raw in (given or {}).items()}


def save(db: Session, plugin: Plugin, user_id: int, given: Dict[str, Any]) -> None:
    """Stores what the person sent. A secret left empty keeps its stored value; any other empty value is cleared
    (the default applies again). Keys that were not sent stay as they are. Missing required values are refused."""
    clean = check(plugin, given)
    rows = _rows(db, plugin.id, user_id)
    for key, value in clean.items():
        spec = spec_of(plugin, key)
        if value == "":
            if not spec.secret and key in rows:
                db.delete(rows[key])
            continue
        row = rows.get(key) or PluginUserSetting(plugin_id=plugin.id, user_id=user_id, key=key)
        row.value = encrypt(value) if spec.secret else value
        row.secret = spec.secret
        db.add(row)
    db.flush()
    missing = []
    for s in plugin.personal_settings:
        if s.required and s.type != "bool" and not get_value(db, plugin, user_id, s.key):
            missing.append(s.key)
    if missing:
        db.rollback()
        raise ValueError(f"Pflichtfelder fehlen: {', '.join(missing)}")
    db.commit()


def resolve(db: Session, plugin: Plugin, user_id: int, given: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Values for a connection test: what was typed, with stored values for secrets left empty and for keys not
    sent. Nothing is saved."""
    typed = check(plugin, given or {})
    current = values(db, plugin, user_id)
    out = {}
    for s in plugin.personal_settings:
        value = typed.get(s.key)
        out[s.key] = current[s.key] if value is None or (s.secret and value == "") else value
    return out


def delete_for_plugin(db: Session, plugin_id: str) -> None:
    db.query(PluginUserSetting).filter(PluginUserSetting.plugin_id == plugin_id).delete(synchronize_session=False)
    db.commit()


def delete_for_user(db: Session, user_id: int) -> None:
    db.query(PluginUserSetting).filter(PluginUserSetting.user_id == user_id).delete(synchronize_session=False)


def prune(db: Session, plugin: Plugin) -> None:
    """Drops values of keys the (updated) plugin no longer declares."""
    keep = [s.key for s in plugin.personal_settings]
    q = db.query(PluginUserSetting).filter(PluginUserSetting.plugin_id == plugin.id)
    if keep:
        q = q.filter(PluginUserSetting.key.notin_(keep))
    q.delete(synchronize_session=False)
    db.commit()
