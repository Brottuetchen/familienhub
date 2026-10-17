"""Farbschemata für die App (#36).

- ``GET /api/themes``: mitgelieferte und installierte Schemata (angemeldet). Welches eine Person nutzt,
  speichert die App pro Gerät.
- ``POST /api/themes``: Installation aus GitHub, nur Admins. Erlaubt ist ausschließlich
  ``https://raw.githubusercontent.com`` (oder eine github.com-Adresse, die dorthin umgeschrieben wird),
  ohne Weiterleitungen, höchstens 64 KB, strenges Schema (nur Hex-Farben, bekannte Felder).
- ``DELETE /api/themes/{id}``: installierte Schemata entfernen, nur Admins.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_min_role
from app.models.theme import Theme
from app.models.user import ROLE_ADMIN, User

router = APIRouter(prefix="/api/themes", tags=["themes"])

BUILTIN_DIR = Path(__file__).resolve().parent.parent / "themes"
REQUIRED_COLORS = ("primary", "secondary", "background", "surface", "surfaceHigh", "border")
OPTIONAL_COLORS = ("onPrimary", "onSecondary", "onBackground", "onSurface")
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
MAX_BYTES = 64 * 1024
RAW_HOST = "raw.githubusercontent.com"
SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


def validate_theme(raw: Any) -> Dict[str, Any]:
    """Nur bekannte Felder, nur Hex-Farben. Alles andere fällt weg oder führt zu 422."""
    if not isinstance(raw, dict):
        raise ValueError("theme.json muss ein Objekt sein")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 60:
        raise ValueError("Name fehlt oder ist länger als 60 Zeichen")
    colors = raw.get("colors")
    if not isinstance(colors, dict):
        raise ValueError("colors fehlt")
    out = {}
    for key in REQUIRED_COLORS + OPTIONAL_COLORS:
        value = colors.get(key)
        if value is None and key in OPTIONAL_COLORS:
            continue
        if not isinstance(value, str) or not HEX.match(value):
            raise ValueError(f"Farbe {key} fehlt oder ist kein #RRGGBB-Wert")
        out[key] = value.upper()
    return {"name": name.strip(), "colors": out, "style": validate_style(raw.get("style") or {})}


def _hex_list(value: Any, field: str, limit: int) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > limit or not all(isinstance(v, str) and HEX.match(v) for v in value):
        raise ValueError(f"{field}: höchstens {limit} #RRGGBB-Farben")
    return [v.upper() for v in value]


def _choice(value: Any, allowed: tuple, default: Any, field: str) -> Any:
    if value is None:
        return default
    if value not in allowed:
        raise ValueError(f"{field}: erlaubt sind {', '.join(map(str, allowed))}")
    return value


def _int(value: Any, lo: int, hi: int, default: int, field: str, step: int = 1) -> int:
    if value is None:
        return default
    if type(value) is not int or not lo <= value <= hi or value % step:
        raise ValueError(f"{field}: ganze Zahl von {lo} bis {hi}")
    return value


def validate_style(raw: Any) -> Dict[str, Any]:
    """Designsprache: nur feste Auswahlwerte, Zahlen in Grenzen, Hex-Farben. Kein CSS, kein Freitext."""
    if not isinstance(raw, dict):
        raise ValueError("style muss ein Objekt sein")
    bg = raw.get("background") or {}
    card = raw.get("card") or {}
    if not isinstance(bg, dict) or not isinstance(card, dict):
        raise ValueError("style.background und style.card müssen Objekte sein")
    glass = card.get("glass", False)
    upper = raw.get("uppercaseTitles", False)
    if not isinstance(glass, bool) or not isinstance(upper, bool):
        raise ValueError("glass und uppercaseTitles sind true/false")
    return {
        "background": {
            "type": _choice(bg.get("type"), ("solid", "gradient", "glow"), "solid", "background.type"),
            "colors": _hex_list(bg.get("colors"), "background.colors", 4),
        },
        "card": {
            "radius": _int(card.get("radius"), 0, 40, 20, "card.radius"),
            "border": _int(card.get("border"), 0, 4, 1, "card.border"),
            "shadow": _choice(card.get("shadow"), ("none", "soft", "hard"), "none", "card.shadow"),
            "glass": glass,
            "header": _choice(card.get("header"), ("plain", "band"), "plain", "card.header"),
        },
        "accents": _hex_list(raw.get("accents"), "accents", 6),
        "nav": _choice(raw.get("nav"), ("bar", "floating"), "bar", "nav"),
        "layout": _choice(raw.get("layout"), ("list", "bento"), "list", "layout"),
        "titleWeight": _int(raw.get("titleWeight"), 400, 900, 500, "titleWeight", step=100),
        "uppercaseTitles": upper,
    }


@lru_cache
def builtin_themes() -> List[Dict[str, Any]]:
    items = []
    for path in sorted(BUILTIN_DIR.glob("*.json")):
        theme = validate_theme(json.loads(path.read_text(encoding="utf-8")))
        items.append({"id": f"builtin:{path.stem}", "builtin": True, **theme})
    return items


def _custom(t: Theme) -> Dict[str, Any]:
    return {"id": f"custom:{t.id}", "builtin": False, "source_url": t.source_url, **json.loads(t.data)}


def raw_url(url: str) -> str:
    """github.com/<owner>/<repo>[/tree|blob/<ref>/<pfad>] oder raw-Adresse → geprüfte raw-URL auf theme.json."""
    parts = urlsplit(url.strip())
    if parts.scheme != "https" or parts.username or parts.password or parts.port or parts.query or parts.fragment:
        raise ValueError("Nur https-Adressen von GitHub ohne Zusätze")
    segs = [s for s in parts.path.split("/") if s]
    if any(not SEGMENT.match(s) or s in (".", "..") for s in segs):
        raise ValueError("Ungültiger Pfad")
    host = (parts.hostname or "").lower()
    if host == "github.com":
        if len(segs) < 2:
            raise ValueError("GitHub-Adresse braucht Besitzer und Repository")
        owner, repo, rest = segs[0], segs[1], segs[2:]
        if rest[:1] in (["tree"], ["blob"]):
            rest = rest[1:]
        if not rest:
            rest = ["main"]
        segs = [owner, repo, *rest]
    elif host != RAW_HOST:
        raise ValueError("Nur Themes von GitHub (raw.githubusercontent.com)")
    if len(segs) < 3:
        raise ValueError("Adresse braucht Besitzer, Repository und Branch")
    if segs[-1] != "theme.json":
        segs.append("theme.json")
    return f"https://{RAW_HOST}/" + "/".join(segs)


def _transport() -> Optional[httpx.AsyncBaseTransport]:
    return None  # Tests ersetzen das durch einen MockTransport


async def fetch_theme(url: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=10, follow_redirects=False, transport=_transport()) as client:
        async with client.stream("GET", url) as resp:
            if resp.status_code != 200:
                raise ValueError(f"GitHub antwortet {resp.status_code}")
            body = b""
            async for chunk in resp.aiter_bytes():
                body += chunk
                if len(body) > MAX_BYTES:
                    raise ValueError("theme.json ist größer als 64 KB")
    try:
        return validate_theme(json.loads(body))
    except json.JSONDecodeError as exc:
        raise ValueError("theme.json ist kein gültiges JSON") from exc


@router.get("")
async def list_themes(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    custom = [_custom(t) for t in db.query(Theme).order_by(Theme.name).all()]
    return {"items": builtin_themes() + custom}


class InstallRequest(BaseModel):
    url: str = Field(min_length=1, max_length=500)


@router.post("", status_code=status.HTTP_201_CREATED)
async def install_theme(data: InstallRequest, db: Session = Depends(get_db),
                        user: User = Depends(require_min_role(ROLE_ADMIN))):
    try:
        url = raw_url(data.url)
        theme = await fetch_theme(url)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(422, "GitHub nicht erreichbar") from exc
    taken = {t["name"].lower() for t in builtin_themes()} | {t.name.lower() for t in db.query(Theme).all()}
    if theme["name"].lower() in taken:
        raise HTTPException(409, f"Ein Theme „{theme['name']}“ gibt es schon")
    row = Theme(name=theme["name"], source_url=url, data=json.dumps(theme), created_by=user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _custom(row)


@router.delete("/{theme_id}")
async def delete_theme(theme_id: str, db: Session = Depends(get_db),
                       _: User = Depends(require_min_role(ROLE_ADMIN))):
    if not theme_id.startswith("custom:"):
        raise HTTPException(403, "Mitgelieferte Themes lassen sich nicht löschen")
    try:
        row = db.get(Theme, int(theme_id.split(":", 1)[1]))
    except ValueError:
        row = None
    if row is None:
        raise HTTPException(404, "Theme nicht gefunden")
    db.delete(row)
    db.commit()
    return {"deleted": True}
