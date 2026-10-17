from app.plugins.base import Plugin, Setting


class ShelfarrPlugin(Plugin):
    """Bücher und Hörbücher wünschen über Shelfarr."""

    def __init__(self):
        super().__init__(
            id="shelfarr",
            name="Shelfarr",
            description="E-Books und Hörbücher suchen und wünschen.",
            capabilities=frozenset({"books"}),
            settings=(
                Setting("SHELFARR_URL", "Adresse"),
                Setting("SHELFARR_TOKEN", "API-Token (Admin, Scopes search/requests)", secret=True),
                Setting("SHELFARR_LANGUAGE", "Sprache", required=False, help="Standard: de"),
                Setting("SHELFARR_USER_MAP", "Nutzer-Zuordnung hub=shelfarr,…", required=False,
                        help="Nur nötig, wenn Benutzernamen abweichen."),
            ),
            builtin=True,
        )

    def routers(self):
        from app.routers import books

        return [books.router]
