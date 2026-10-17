from app.plugins.base import Plugin, Setting


class SeerrPlugin(Plugin):
    """Filme und Serien wünschen über Seerr (Jellyseerr/Overseerr)."""

    def __init__(self):
        super().__init__(
            id="seerr",
            name="Seerr",
            description="Filme und Serien suchen, wünschen und den Stand sehen – als eigener Seerr-Nutzer.",
            capabilities=frozenset({"media_requests"}),
            settings=(
                Setting("SEERR_URL", "Adresse (vom Server aus erreichbar)", help="z. B. http://seerr.lan:5055"),
                Setting("SEERR_API_KEY", "API-Schlüssel (Einstellungen → Allgemein)", secret=True),
                Setting("SEERR_USER_MAP", "Nutzer-Zuordnung hub=seerr,…", required=False,
                        help="Nur nötig, wenn Benutzernamen abweichen (Seerr-Name, Jellyfin-Name oder E-Mail)."),
            ),
            builtin=True,
        )

    def routers(self):
        from app.routers import media

        return [media.router]
