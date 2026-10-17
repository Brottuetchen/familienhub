"""Wetter-Connector auf Basis von Open-Meteo (kostenlos, ohne API-Key).

Funktioniert out-of-the-box und liefert echte Daten – Grundlage für
proaktive Hinweise wie "Morgen regnet es → Fahrradfahrt absagen?".
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.config import settings
from app.connectors.base import BaseConnector

# WMO Weather Interpretation Codes -> (Beschreibung, Emoji)
WMO_CODES: Dict[int, tuple[str, str]] = {
    0: ("Klarer Himmel", "☀️"),
    1: ("Überwiegend klar", "🌤️"),
    2: ("Teilweise bewölkt", "⛅"),
    3: ("Bewölkt", "☁️"),
    45: ("Nebel", "🌫️"),
    48: ("Reifnebel", "🌫️"),
    51: ("Leichter Nieselregen", "🌦️"),
    53: ("Nieselregen", "🌦️"),
    55: ("Starker Nieselregen", "🌧️"),
    56: ("Gefrierender Nieselregen", "🌧️"),
    57: ("Starker gefrierender Nieselregen", "🌧️"),
    61: ("Leichter Regen", "🌦️"),
    63: ("Regen", "🌧️"),
    65: ("Starker Regen", "🌧️"),
    66: ("Gefrierender Regen", "🌧️"),
    67: ("Starker gefrierender Regen", "🌧️"),
    71: ("Leichter Schneefall", "🌨️"),
    73: ("Schneefall", "🌨️"),
    75: ("Starker Schneefall", "❄️"),
    77: ("Schneegriesel", "🌨️"),
    80: ("Leichte Regenschauer", "🌦️"),
    81: ("Regenschauer", "🌧️"),
    82: ("Heftige Regenschauer", "⛈️"),
    85: ("Leichte Schneeschauer", "🌨️"),
    86: ("Schneeschauer", "❄️"),
    95: ("Gewitter", "⛈️"),
    96: ("Gewitter mit Hagel", "⛈️"),
    99: ("Schweres Gewitter mit Hagel", "⛈️"),
}


def describe_code(code: Optional[int]) -> tuple[str, str]:
    if code is None:
        return ("Unbekannt", "❓")
    return WMO_CODES.get(int(code), ("Unbekannt", "❓"))


class WeatherConnector(BaseConnector):
    name = "weather"
    display_name = "Wetter"
    category = "weather"
    icon = "🌤️"

    API_HOST = "https://api.open-meteo.com"

    @property
    def is_configured(self) -> bool:
        # Open-Meteo braucht keinen Key -> nur ein Feature-Flag.
        return bool(settings.weather_enabled)

    @property
    def base_url(self) -> Optional[str]:
        return self.API_HOST

    async def _probe(self) -> bool:
        data = await self.get_current()
        return bool(data)

    async def _forecast(self) -> Dict[str, Any]:
        params = {
            "latitude": settings.weather_latitude,
            "longitude": settings.weather_longitude,
            "current": "temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m,apparent_temperature",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset",
            "timezone": "auto",
            "forecast_days": 7,
        }
        return await self._get_json("/v1/forecast", params=params)

    async def get_current(self) -> Dict[str, Any]:
        """Aktuelles Wetter am konfigurierten Standort."""
        if not self.is_configured:
            return {}
        try:
            data = await self._forecast()
            cur = data.get("current", {})
            desc, emoji = describe_code(cur.get("weather_code"))
            return {
                "location": settings.weather_location_name,
                "temperature": cur.get("temperature_2m"),
                "apparent_temperature": cur.get("apparent_temperature"),
                "humidity": cur.get("relative_humidity_2m"),
                "wind_speed": cur.get("wind_speed_10m"),
                "code": cur.get("weather_code"),
                "description": desc,
                "icon": emoji,
            }
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("weather current failed: %s", exc)
            return {}

    async def get_forecast(self, days: int = 5) -> List[Dict[str, Any]]:
        """Tagesvorhersage."""
        if not self.is_configured:
            return []
        try:
            data = await self._forecast()
            daily = data.get("daily", {})
            times = daily.get("time", [])
            out: List[Dict[str, Any]] = []
            for i, day in enumerate(times[:days]):
                desc, emoji = describe_code(_at(daily.get("weather_code"), i))
                out.append(
                    {
                        "date": day,
                        "temp_max": _at(daily.get("temperature_2m_max"), i),
                        "temp_min": _at(daily.get("temperature_2m_min"), i),
                        "precip_probability": _at(daily.get("precipitation_probability_max"), i),
                        "code": _at(daily.get("weather_code"), i),
                        "description": desc,
                        "icon": emoji,
                    }
                )
            return out
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("weather forecast failed: %s", exc)
            return []

    async def will_rain_tomorrow(self) -> Optional[bool]:
        """Proaktiver Hinweis-Helfer: Regnet es morgen wahrscheinlich?"""
        forecast = await self.get_forecast(days=2)
        if len(forecast) < 2:
            return None
        tomorrow = forecast[1]
        prob = tomorrow.get("precip_probability")
        code = tomorrow.get("code") or 0
        rainy_codes = {51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99}
        return bool((prob is not None and prob >= 50) or int(code) in rainy_codes)


def _at(seq: Optional[List[Any]], idx: int) -> Any:
    if not seq or idx >= len(seq):
        return None
    return seq[idx]
