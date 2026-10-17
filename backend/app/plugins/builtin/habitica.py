"""Optionale Habitica-Aufgabenanbindung ohne Übernahme der Nextcloud-Fähigkeit."""
from app.plugins.base import Plugin, Setting


class HabiticaPlugin(Plugin):
    def __init__(self):
        super().__init__(id="habitica", name="Habitica", builtin=True, capabilities=frozenset({"tasks"}),
                         description="Ausgewählte persönliche Aufgaben bidirektional anbinden",
                         settings=(Setting("HABITICA_URL", "Habitica-Server", help="HTTPS-Basisadresse ohne /api/v3"),
                                   Setting("HABITICA_NATIVE_WRITE_ACCOUNTS", "Geprüfter Single-Writer-Übergang: Server|Konto-UUID", required=False,
                                           help="Nur Betreiber: erst nach Backup, verifiziertem Cron-/Prozessstop und Bestandsabgleich freigeben. Standard leer.")))

    def task_connector(self, user_id, db):
        from app.connectors.habitica_connector import HabiticaConnector
        return HabiticaConnector(user_id, db)

    def routers(self):
        from app.routers.habitica import router
        return [router]
