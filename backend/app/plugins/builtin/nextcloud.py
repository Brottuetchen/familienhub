from app.plugins.base import Plugin, Setting, get_setting


class NextcloudPlugin(Plugin):
    """Aufgaben (VTODO) und Termine per CalDAV. Zugangsdaten hinterlegt jede Person selbst in der App."""

    def __init__(self):
        super().__init__(
            id="nextcloud",
            name="CalDAV (Nextcloud, iCloud, Radicale …)",
            description="Aufgaben und Termine von jedem CalDAV-Server (Nextcloud, iCloud, mailbox.org, Radicale …), Konto pro Person.",
            capabilities=frozenset({"tasks", "calendar"}),
            settings=(
                Setting("CALDAV_URL", "Gemeinsamer Kalender: CalDAV-Adresse", required=False,
                        help="Optional. Fallback für Personen ohne eigenes Konto."),
                Setting("CALDAV_USERNAME", "Gemeinsamer Kalender: Benutzer", required=False),
                Setting("CALDAV_PASSWORD", "Gemeinsamer Kalender: Passwort", secret=True, required=False),
                Setting("CALDAV_FAMILY_CALENDAR", "Name des Familienkalenders", required=False,
                        help="So heißt der geteilte Familienkalender in Nextcloud o. Ä. (mehrere mit Komma). Er wird beim Anlegen vorgeschlagen."),
            ),
            builtin=True,
            family_tasks=True,
        )

    def is_configured(self) -> bool:
        return True  # Konten pro Person; ohne Konto zeigt die App einen Hinweis

    def is_set_up(self) -> bool:
        """Set up for the wizard once a shared calendar is stored; personal accounts come later in the app."""
        return bool(get_setting("CALDAV_URL"))

    def task_connector(self, user_id, db):
        from app.connectors.nextcloud_tasks_connector import NextcloudTasksConnector
        return NextcloudTasksConnector(user_id=user_id)
