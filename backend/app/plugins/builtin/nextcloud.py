from app.plugins.base import Plugin, Setting


class NextcloudPlugin(Plugin):
    """Aufgaben (VTODO) und Termine per CalDAV. Zugangsdaten hinterlegt jede Person selbst in der App."""

    def __init__(self):
        super().__init__(
            id="nextcloud",
            name="Nextcloud / CalDAV",
            description="Aufgaben und Termine aus Nextcloud (oder jedem CalDAV-Server), Konto pro Person.",
            capabilities=frozenset({"tasks", "calendar"}),
            settings=(
                Setting("CALDAV_URL", "Gemeinsamer Kalender: CalDAV-Adresse", required=False,
                        help="Optional. Fallback für Personen ohne eigenes Konto."),
                Setting("CALDAV_USERNAME", "Gemeinsamer Kalender: Benutzer", required=False),
                Setting("CALDAV_PASSWORD", "Gemeinsamer Kalender: Passwort", secret=True, required=False),
            ),
            builtin=True,
        )

    def is_configured(self) -> bool:
        return True  # Konten pro Person; ohne Konto zeigt die App einen Hinweis

    def task_connector(self, user_id, db):
        from app.connectors.nextcloud_tasks_connector import NextcloudTasksConnector
        return NextcloudTasksConnector(user_id=user_id)

    def routers(self):
        from app.routers import calendar

        return [calendar.router]
