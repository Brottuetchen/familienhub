from app.config import settings
from app.plugins.base import Plugin, Setting


class WeatherPlugin(Plugin):
    """Wetter in „Heute“ über Open-Meteo (kein Schlüssel nötig)."""

    def __init__(self):
        super().__init__(
            id="weather",
            name="Wetter (Open-Meteo)",
            description="Aktuelles Wetter für „Heute“.",
            capabilities=frozenset({"weather"}),
            settings=(
                Setting("WEATHER_LATITUDE", "Breitengrad", required=False),
                Setting("WEATHER_LONGITUDE", "Längengrad", required=False),
                Setting("WEATHER_LOCATION_NAME", "Ortsname", required=False),
            ),
            builtin=True,
        )

    def is_configured(self) -> bool:
        return bool(settings.weather_enabled)
