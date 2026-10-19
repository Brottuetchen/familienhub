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
        """Set up once coordinates were saved (or set in the environment); without them the built-in
        default location is used as long as WEATHER_ENABLED is not switched off."""
        return self._explicit() or bool(settings.weather_enabled)

    def is_set_up(self) -> bool:
        return self._explicit()

    @staticmethod
    def _explicit() -> bool:
        from app.services.config_store import was_saved

        if all(was_saved(k) for k in ("WEATHER_LATITUDE", "WEATHER_LONGITUDE")):
            return True
        fields = type(settings).model_fields
        return (settings.weather_latitude != fields["weather_latitude"].default
                or settings.weather_longitude != fields["weather_longitude"].default)

    async def check(self):
        if not self.active:
            return None
        place = settings.weather_location_name
        return {"status": "ok", "message": f"Eingerichtet ({place})" if self._explicit() else "Eingerichtet (Standardort)"}
