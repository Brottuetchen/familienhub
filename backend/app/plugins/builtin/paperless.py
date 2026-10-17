from app.plugins.base import Plugin, Setting


class PaperlessPlugin(Plugin):
    """Dokumente aus Paperless-ngx: Suche, neueste, Fristen. Jede Person mit eigenem Zugang."""

    def __init__(self):
        super().__init__(
            id="paperless",
            name="Paperless-ngx",
            description="Dokumente suchen, neueste ansehen, Fristen als Erinnerung – mit dem eigenen Paperless-Zugang.",
            capabilities=frozenset({"documents"}),
            settings=(
                Setting("PAPERLESS_URL", "Adresse (vom Server aus erreichbar)", help="z. B. http://paperless.lan:8000"),
                Setting("PAPERLESS_PUBLIC_URL", "Adresse für Links in der App", required=False,
                        help="Öffentliche/interne Adresse zum Öffnen im Browser; leer = wie oben"),
            ),
            builtin=True,
        )

    def routers(self):
        from app.routers import paperless

        return [paperless.router]
