"""„Verbindung testen“ (#4): echter Test je Plugin mit den eingegebenen (noch nicht gespeicherten) Werten.

Prüft Anmeldung, nicht nur Erreichbarkeit. Antworten enthalten nie Zugangsdaten, Adressen oder
Antwortinhalte der Dienste – nur eine kurze deutsche Meldung.
"""

from __future__ import annotations

from typing import Awaitable, Callable, Dict, Optional

import httpx

from app.plugins.base import get_setting

Result = Dict[str, object]
TIMEOUT = 8


def ok(message: str) -> Result:
    return {"ok": True, "level": "ok", "message": message}


def info(message: str) -> Result:
    return {"ok": True, "level": "info", "message": message}


def fail(message: str) -> Result:
    return {"ok": False, "level": "error", "message": message}


def resolve(plugin, values: Optional[Dict[str, str]]) -> Dict[str, str]:
    """Eingaben haben Vorrang; leere Geheimnisse bedeuten „gespeicherten Wert behalten“."""
    values = {k.upper(): (v or "").strip() for k, v in (values or {}).items()}
    out: Dict[str, str] = {}
    for s in plugin.settings:
        given = values.get(s.key.upper())
        if given is None or (s.secret and given == ""):
            out[s.key.upper()] = str(get_setting(s.key) or "").strip()
        else:
            out[s.key.upper()] = given
    return out


async def _get(url: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
        return await client.request(kwargs.pop("method", "GET"), url, **kwargs)


def _base(v: Dict[str, str], key: str) -> str:
    return v.get(key, "").rstrip("/")


def _auth_status(code: int, service: str, what: str = "Token") -> Result:
    if code in (401, 403):
        return fail(f"{service} erreichbar, aber {what} ungültig")
    if code == 404:
        return fail(f"{service}: Adresse stimmt nicht (nichts gefunden)")
    return fail(f"{service} antwortet mit Fehler {code}")


async def _homeassistant(v):
    url, token = _base(v, "HOMEASSISTANT_URL"), v.get("HOMEASSISTANT_TOKEN", "")
    if not url or not token:
        return fail("Adresse und Token eintragen")
    r = await _get(f"{url}/api/", headers={"Authorization": f"Bearer {token}"})
    return ok("Home Assistant: verbunden, Token gültig") if r.status_code == 200 else _auth_status(r.status_code, "Home Assistant")


async def _nextcloud(v):
    url = _base(v, "CALDAV_URL")
    if not url:
        return info("Kein gemeinsamer Kalender eingetragen. Nextcloud-Konten verbindet jede Person selbst in der App.")
    r = await _get(url, method="PROPFIND", headers={"Depth": "0"},
                   auth=(v.get("CALDAV_USERNAME", ""), v.get("CALDAV_PASSWORD", "")))
    if r.status_code in (200, 207):
        return ok("Gemeinsamer Kalender: verbunden")
    return _auth_status(r.status_code, "Kalender", "Benutzer oder Passwort")


async def _habitica(v):
    url = _base(v, "HABITICA_URL") or "https://habitica.com"
    r = await _get(f"{url}/api/v3/status")
    up = r.status_code == 200 and (r.json().get("data") or {}).get("status") == "up"
    return ok("Habitica erreichbar. Konten verbindet jede Person selbst.") if up else fail("Habitica antwortet nicht wie erwartet")


async def _paperless(v):
    url = _base(v, "PAPERLESS_URL")
    if not url:
        return fail("Adresse eintragen")
    r = await _get(f"{url}/api/")
    if r.status_code in (200, 401, 403):
        return ok("Paperless erreichbar. Den Zugang verbindet jede Person mit ihrem eigenen Token.")
    return _auth_status(r.status_code, "Paperless")


async def _shelfarr(v):
    url, token = _base(v, "SHELFARR_URL"), v.get("SHELFARR_TOKEN", "")
    if not url or not token:
        return fail("Adresse und API-Token eintragen")
    r = await _get(f"{url}/api/v1/requests", params={"limit": 1}, headers={"Authorization": f"Bearer {token}"})
    return ok("Shelfarr: verbunden, Token gültig") if r.status_code == 200 else _auth_status(r.status_code, "Shelfarr")


async def _seerr(v):
    url, key = _base(v, "SEERR_URL"), v.get("SEERR_API_KEY", "")
    if not url or not key:
        return fail("Adresse und API-Schlüssel eintragen")
    r = await _get(f"{url}/api/v1/settings/main", headers={"X-Api-Key": key})
    return ok("Seerr: verbunden, Schlüssel gültig") if r.status_code == 200 else _auth_status(r.status_code, "Seerr", "Schlüssel")


async def _weather(v):
    try:
        lat, lon = float(v.get("WEATHER_LATITUDE") or "x"), float(v.get("WEATHER_LONGITUDE") or "x")
    except ValueError:
        return fail("Breiten- und Längengrad als Zahl eintragen, z. B. 52.52 und 13.405")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return fail("Koordinaten außerhalb des gültigen Bereichs")
    r = await _get("https://api.open-meteo.com/v1/forecast",
                   params={"latitude": lat, "longitude": lon, "current": "temperature_2m"})
    if r.status_code != 200:
        return fail("Wetterdienst gerade nicht erreichbar")
    temp = (r.json().get("current") or {}).get("temperature_2m")
    place = v.get("WEATHER_LOCATION_NAME") or "dort"
    return ok(f"Wetter: gerade {temp} °C in {place}" if temp is not None else "Wetterdienst erreichbar")


async def _cookidoo(v):
    from app.services import cookidoo

    email, password = v.get("COOKIDOO_EMAIL", ""), v.get("COOKIDOO_PASSWORD", "")
    if not email or not password:
        return fail("E-Mail und Passwort eintragen")
    cfg = {"email": email, "password": password, "country": (v.get("COOKIDOO_COUNTRY") or "de").lower(),
           "language": v.get("COOKIDOO_LANGUAGE") or "de-DE"}
    client = None
    try:
        client = await cookidoo._default_factory(cfg)
        await client.login()
        return ok("Cookidoo: Anmeldung erfolgreich")
    except cookidoo.CookidooUnavailable as exc:
        return fail(str(exc))
    except Exception as exc:  # noqa: BLE001 – Bibliothek wirft eigene Fehlerklassen
        name = type(exc).__name__.lower()
        return fail("Cookidoo: E-Mail oder Passwort falsch" if "auth" in name else "Cookidoo gerade nicht erreichbar")
    finally:
        session = getattr(client, "_session", None)
        if session is not None:
            await session.close()


async def _reachable(plugin, v):
    url = next((v[s.key.upper()] for s in plugin.settings
                if s.key.endswith("_URL") and not s.key.endswith("PUBLIC_URL") and v.get(s.key.upper())), "")
    if not url:
        return info("Für dieses Plugin gibt es keinen Verbindungstest")
    r = await _get(url)
    return ok("Erreichbar") if r.status_code < 500 else fail(f"Antwortet mit Fehler {r.status_code}")


TESTERS: Dict[str, Callable[[Dict[str, str]], Awaitable[Result]]] = {
    "homeassistant": _homeassistant, "nextcloud": _nextcloud, "habitica": _habitica, "paperless": _paperless,
    "shelfarr": _shelfarr, "seerr": _seerr, "weather": _weather, "cookidoo": _cookidoo,
}


async def run(plugin, values: Optional[Dict[str, str]]) -> Result:
    v = resolve(plugin, values)
    tester = TESTERS.get(plugin.id)
    try:
        return await (tester(v) if tester else _reachable(plugin, v))
    except httpx.InvalidURL:
        return fail("Adresse ungültig – mit http:// oder https:// angeben")
    except httpx.TimeoutException:
        return fail("Zeitüberschreitung – Adresse und Netzwerk prüfen")
    except httpx.HTTPError:
        return fail("Nicht erreichbar – Adresse prüfen (vom Server aus erreichbar?)")
    except ValueError:
        return fail("Unerwartete Antwort – ist das die richtige Adresse?")
