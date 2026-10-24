"""``familienhub-plugin.json``: the manifest of an installable plugin.

The manifest is the single source of truth for the installer: what the plugin is called, where its
Python package lives, which entry point to load and which settings the admin has to fill in. It is
validated strictly (types, lengths, unknown keys rejected) before anything is downloaded or installed.
Errors are German (like all server texts, translated in ``app/core/i18n.py``).
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from app.plugins.base import CAPABILITIES, Setting

MANIFEST_FILE = "familienhub-plugin.json"
MAX_MANIFEST_BYTES = 64 * 1024

ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,60}$")
VERSION_RE = re.compile(r"^[0-9][0-9A-Za-z.+_-]{0,31}$")
ENTRY_POINT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*:[A-Za-z_][A-Za-z0-9_]*$")
HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?(:\d{1,5})?$")
PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SETTING_TYPES = ("text", "url", "password", "number", "bool")
LANGUAGES = ("de", "en")

TOP_KEYS = {"id", "name", "version", "description", "author", "homepage", "license", "min_hub_version", "package",
            "entry_point", "settings", "hosts", "capabilities"}
REQUIRED_KEYS = ("id", "name", "version", "description", "author", "entry_point")
SETTING_KEYS = {"key", "label", "help", "type", "secret", "required", "default", "example"}

# Words that belong to the core or to the built-in plugins; an installed plugin may not use them as its id
# (its setting keys all start with "<ID>_", which must never reach a core or built-in setting).
_EXTRA_RESERVED = ("hub", "plugin", "plugins", "caldav", "fh", "alembic", "database", "app", "oidc", "vapid", "fcm",
                   "secret", "data", "cors", "access", "refresh", "setup")

Text = Union[str, Dict[str, str]]


def _reserved_tokens() -> set:
    from app.config import Settings
    from app.plugins.builtin import BUILTIN_PLUGINS
    from app.services.config_store import _core_settings

    tokens = set(_EXTRA_RESERVED) | set(CAPABILITIES)
    tokens |= {p.id.split("_")[0] for p in BUILTIN_PLUGINS} | {p.id for p in BUILTIN_PLUGINS}
    tokens |= {name.split("_")[0] for name in Settings.model_fields}
    tokens |= {s.key.split("_")[0].lower() for s in _core_settings()}
    tokens |= {s.key.split("_")[0].lower() for p in BUILTIN_PLUGINS for s in p.settings}
    return tokens


def is_reserved_id(plugin_id: str) -> bool:
    return any(plugin_id == t or plugin_id.startswith(t + "_") for t in _reserved_tokens())


def _text(value: Any, field: str, *, max_len: int, required: bool = True) -> Optional[Text]:
    """A string, or ``{"de": …, "en": …}`` (at least one of them)."""
    if value is None:
        if required:
            raise ValueError(f"Manifest: {field} fehlt")
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value and required:
            raise ValueError(f"Manifest: {field} fehlt")
        if len(value) > max_len:
            raise ValueError(f"Manifest: {field} ist länger als {max_len} Zeichen")
        return value
    if isinstance(value, dict):
        if not value or set(value) - set(LANGUAGES):
            raise ValueError(f"Manifest: {field} erlaubt nur die Sprachen de und en")
        out = {}
        for lang, text in value.items():
            if not isinstance(text, str) or not text.strip() or len(text.strip()) > max_len:
                raise ValueError(f"Manifest: {field}.{lang} ist leer oder länger als {max_len} Zeichen")
            out[lang] = text.strip()
        return out
    raise ValueError(f"Manifest: {field} muss Text oder ein Objekt mit de und en sein")


def localized(value: Any, lang: str) -> str:
    """Text in ``lang``; falls back to German, then English."""
    if isinstance(value, dict):
        return str(value.get(lang) or value.get("de") or value.get("en") or "")
    return str(value or "")


def german(value: Any) -> str:
    return localized(value, "de")


def english(value: Any) -> str:
    return localized(value, "en") if isinstance(value, dict) and value.get("en") else german(value)


def _string(value: Any, field: str, *, max_len: int, required: bool = True) -> Optional[str]:
    if not required and (value is None or value == ""):
        return None
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError(f"Manifest: {field} fehlt oder ist kein Text")
    value = value.strip()
    if len(value) > max_len:
        raise ValueError(f"Manifest: {field} ist länger als {max_len} Zeichen")
    return value


def _bool(value: Any, field: str, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"Manifest: {field} muss true oder false sein")
    return value


def _scalar_default(value: Any, kind: str, field: str) -> Optional[str]:
    """Default as the string the hub stores; checked against the setting's type."""
    if value is None:
        return None
    if kind == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"Manifest: {field} (Vorgabe) muss true oder false sein")
        return "true" if value else "false"
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Manifest: {field} (Vorgabe) muss eine Zahl sein")
        return str(value)
    if not isinstance(value, str) or len(value) > 300:
        raise ValueError(f"Manifest: {field} (Vorgabe) muss Text bis 300 Zeichen sein")
    if kind == "url":
        check_value("url", value, field)
    return value


def check_value(kind: str, value: str, field: str) -> str:
    """Validate an admin's input for a setting of this type; returns the value to store."""
    if len(value) > 2000 or any(c in value for c in "\r\n\x00"):
        raise ValueError(f"Wert von {field} ist ungültig")
    if kind == "url" and value:
        if not re.match(r"^https?://[^\s/?#]+(/\S*)?$", value):
            raise ValueError(f"Wert von {field}: Adresse muss mit http:// oder https:// beginnen")
    elif kind == "number" and value:
        try:
            float(value)
        except ValueError:
            raise ValueError(f"Wert von {field}: keine Zahl") from None
    elif kind == "bool" and value not in ("true", "false"):
        raise ValueError(f"Wert von {field}: nur true oder false")
    return value


def _setting(raw: Any, plugin_id: str, index: int) -> Dict[str, Any]:
    where = f"settings[{index}]"
    if not isinstance(raw, dict):
        raise ValueError(f"Manifest: {where} muss ein Objekt sein")
    unknown = set(raw) - SETTING_KEYS
    if unknown:
        raise ValueError(f"Manifest: {where} hat unbekannte Felder: {', '.join(sorted(map(str, unknown)))}")
    key = raw.get("key")
    prefix = plugin_id.upper() + "_"
    if not isinstance(key, str) or not KEY_RE.match(key) or not key.startswith(prefix) or len(key) == len(prefix):
        raise ValueError(f"Manifest: {where}: Schlüssel muss mit {prefix} beginnen (nur A–Z, 0–9 und _)")
    kind = raw.get("type", "text")
    if kind not in SETTING_TYPES:
        raise ValueError(f"Manifest: {where}: type ist einer von {', '.join(SETTING_TYPES)}")
    secret = _bool(raw.get("secret"), f"{where}.secret", False) or kind == "password"
    required = _bool(raw.get("required"), f"{where}.required", True) and kind != "bool"
    default = _scalar_default(raw.get("default"), kind, f"{where}.default")
    if secret and default is not None:
        raise ValueError(f"Manifest: {where}: geheime Felder dürfen keine Vorgabe haben")
    return {
        "key": key,
        "label": _text(raw.get("label"), f"{where}.label", max_len=60),
        "help": _text(raw.get("help"), f"{where}.help", max_len=300, required=False) or "",
        "type": kind,
        "secret": secret,
        "required": required,
        "default": default,
        "example": _string(raw.get("example"), f"{where}.example", max_len=100, required=False) or "",
    }


def _package_path(value: Any) -> str:
    if value is None:
        return "."
    if not isinstance(value, str) or not value.strip() or len(value) > 100:
        raise ValueError("Manifest: package ist ein Ordner im Repository (Standard „.“)")
    value = value.strip()
    if value.startswith("/") or "\\" in value:
        raise ValueError("Manifest: package hat einen ungültigen Pfad (nur Buchstaben, Ziffern, . _ - und /, kein ..)")
    value = value.strip("/")
    if value in ("", "."):
        return "."
    segments = value.split("/")
    if any(not PATH_SEGMENT_RE.match(s) or s in (".", "..") for s in segments):
        raise ValueError("Manifest: package hat einen ungültigen Pfad (nur Buchstaben, Ziffern, . _ - und /, kein ..)")
    return "/".join(segments)


def validate_manifest(raw: Any) -> Dict[str, Any]:
    """Validated manifest with all defaults filled in. Raises ``ValueError`` (German text) on any problem."""
    if not isinstance(raw, dict):
        raise ValueError(f"Manifest: {MANIFEST_FILE} muss ein JSON-Objekt sein")
    unknown = set(raw) - TOP_KEYS
    if unknown:
        raise ValueError(f"Manifest: unbekannte Felder: {', '.join(sorted(map(str, unknown)))}")
    for key in REQUIRED_KEYS:
        if key not in raw:
            raise ValueError(f"Manifest: Feld {key} fehlt")

    plugin_id = raw["id"]
    if not isinstance(plugin_id, str) or not ID_RE.match(plugin_id):
        raise ValueError("Manifest: id muss kleingeschrieben sein, 2–31 Zeichen (a–z, 0–9, _) und mit einem Buchstaben beginnen")
    if is_reserved_id(plugin_id):
        raise ValueError(f"Manifest: id „{plugin_id}“ ist für den Hub und eingebaute Plugins reserviert")

    version = _string(raw["version"], "version", max_len=32)
    if not VERSION_RE.match(version):
        raise ValueError("Manifest: version muss z. B. 1.2.0 lauten")
    min_hub = _string(raw.get("min_hub_version"), "min_hub_version", max_len=32, required=False)
    if min_hub is not None and not VERSION_RE.match(min_hub):
        raise ValueError("Manifest: min_hub_version muss z. B. 1.0.0 lauten")
    homepage = _string(raw.get("homepage"), "homepage", max_len=200, required=False)
    if homepage and not re.match(r"^https://[^\s/?#]+(/\S*)?$", homepage):
        raise ValueError("Manifest: homepage muss mit https:// beginnen")
    entry_point = _string(raw["entry_point"], "entry_point", max_len=200)
    if not ENTRY_POINT_RE.match(entry_point):
        raise ValueError("Manifest: entry_point hat die Form modul:Klasse, z. B. fh_plugin_demo.plugin:DemoPlugin")

    settings_raw = raw.get("settings", [])
    if not isinstance(settings_raw, list) or len(settings_raw) > 20:
        raise ValueError("Manifest: settings ist eine Liste mit höchstens 20 Einträgen")
    settings = [_setting(s, plugin_id, i) for i, s in enumerate(settings_raw)]
    keys = [s["key"] for s in settings]
    if len(set(keys)) != len(keys):
        raise ValueError("Manifest: settings enthält einen Schlüssel doppelt")

    hosts_raw = raw.get("hosts", [])
    if not isinstance(hosts_raw, list) or len(hosts_raw) > 20 or not all(isinstance(h, str) and HOST_RE.match(h.strip()) for h in hosts_raw):
        raise ValueError("Manifest: hosts ist eine Liste von Hostnamen ohne https://, höchstens 20")
    caps_raw = raw.get("capabilities", [])
    if not isinstance(caps_raw, list) or len(caps_raw) > len(CAPABILITIES) or not all(c in CAPABILITIES for c in caps_raw):
        raise ValueError(f"Manifest: capabilities erlaubt nur {', '.join(CAPABILITIES)}")

    return {
        "id": plugin_id,
        "name": _text(raw["name"], "name", max_len=60),
        "version": version,
        "description": _text(raw["description"], "description", max_len=500),
        "author": _string(raw["author"], "author", max_len=100),
        "homepage": homepage or "",
        "license": _string(raw.get("license"), "license", max_len=60, required=False) or "",
        "min_hub_version": min_hub or "",
        "package": _package_path(raw.get("package")),
        "entry_point": entry_point,
        "settings": settings,
        "hosts": list(dict.fromkeys(h.strip().lower() for h in hosts_raw)),
        "capabilities": list(dict.fromkeys(caps_raw)),
    }


def parse_manifest(body: bytes) -> Dict[str, Any]:
    if len(body) > MAX_MANIFEST_BYTES:
        raise ValueError(f"Manifest: {MANIFEST_FILE} ist größer als 64 KB")
    try:
        raw = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Manifest: {MANIFEST_FILE} ist kein gültiges JSON") from exc
    return validate_manifest(raw)


def load_stored_manifest(text: str) -> Dict[str, Any]:
    """Validate a manifest the hub stored itself (``validate_manifest`` output, defaults kept as strings).

    Bool and number defaults go back to JSON types first, otherwise every stored manifest with such a default
    would fail its own check on restart and update.
    """
    raw = json.loads(text)
    for s in raw.get("settings", []) if isinstance(raw, dict) else []:
        default = s.get("default") if isinstance(s, dict) else None
        if not isinstance(default, str):
            continue
        if s.get("type") == "bool" and default in ("true", "false"):
            s["default"] = default == "true"
        elif s.get("type") == "number":
            try:
                number = float(default)
            except ValueError:
                continue
            s["default"] = int(number) if number.is_integer() and "." not in default else number
    return validate_manifest(raw)


def _version_tuple(value: str) -> Optional[Tuple[int, ...]]:
    m = re.match(r"^(\d+(?:\.\d+)*)", value or "")
    return tuple(int(p) for p in m.group(1).split(".")) if m else None


def _pre_release(value: str) -> Optional[List[Any]]:
    """Pre-release identifiers of "1.0.0-beta.3" as sortable pairs; None for a release."""
    m = re.match(r"^v?\d+(?:\.\d+)*-([0-9A-Za-z.-]+)", value or "")
    if not m:
        return None
    return [(0, int(p), "") if p.isdigit() else (1, 0, p) for p in m.group(1).split(".")]


def hub_version_ok(min_hub_version: str, hub_version: str) -> bool:
    """False only if both versions are numeric and the hub is older. Development builds pass.

    Pre-releases count: ``1.0.0-beta.2`` is older than ``1.0.0-beta.3``, which is older than ``1.0.0``.
    An edge build (``1.0.0-edge+412``, built from main) is newer than every pre-release of its number.
    """
    need, have = _version_tuple(min_hub_version), _version_tuple(hub_version)
    if not need or not have:
        return True
    size = max(len(need), len(have))
    need, have = need + (0,) * (size - len(need)), have + (0,) * (size - len(have))
    if have != need:
        return have > need
    need_pre, have_pre = _pre_release(min_hub_version), _pre_release(hub_version)
    if need_pre is None:  # a release is needed: only a release (or an edge build of it) is enough
        return have_pre is None or str(hub_version).lstrip("v").split("-", 1)[1].startswith("edge")
    if have_pre is None or str(hub_version).lstrip("v").split("-", 1)[1].startswith("edge"):
        return True
    return have_pre >= need_pre


def settings_for(manifest: Dict[str, Any]) -> Tuple[Setting, ...]:
    """The manifest's settings as the hub's own ``Setting`` objects (German label and help)."""
    return tuple(
        Setting(s["key"], german(s["label"]), secret=s["secret"], required=s["required"], help=german(s["help"]))
        for s in manifest["settings"]
    )


def form_spec(manifest: Dict[str, Any], lang: str) -> List[Dict[str, Any]]:
    """The settings form for the app, texts in ``lang``."""
    return [
        {"key": s["key"], "label": localized(s["label"], lang), "help": localized(s["help"], lang), "type": s["type"],
         "secret": s["secret"], "required": s["required"], "default": s["default"], "example": s["example"]}
        for s in manifest["settings"]
    ]
