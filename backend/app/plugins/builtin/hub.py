"""Built-in sources: work without any external service and can be switched off like any plugin."""

from app.plugins.base import Plugin


class HubTasksPlugin(Plugin):
    def __init__(self):
        super().__init__(
            id="hub_tasks",
            name="Aufgaben im Hub",
            description="Aufgaben direkt im Familienhub: privat, füreinander, Familienliste und Haushaltsrotation. Läuft ohne externen Dienst, auch neben Nextcloud oder Habitica.",
            capabilities=frozenset({"tasks"}),
            builtin=True,
            fallback=True,
        )

    def is_configured(self) -> bool:
        return True

    def task_connector(self, user_id, db):
        from app.connectors.hub_tasks_connector import HubTasksConnector

        return HubTasksConnector(user_id)


class HubShoppingPlugin(Plugin):
    def __init__(self):
        super().__init__(
            id="hub_shopping",
            name="Einkaufsliste im Hub",
            description="Gemeinsame Einkaufsliste direkt im Familienhub. Wird genutzt, wenn keine andere Einkaufsquelle aktiv ist oder SHOPPING_SOURCE=hub_shopping gesetzt ist.",
            capabilities=frozenset({"shopping"}),
            builtin=True,
            fallback=True,
        )

    def is_configured(self) -> bool:
        return True


class HubCalendarPlugin(Plugin):
    def __init__(self):
        super().__init__(
            id="hub_calendar",
            name="Familienkalender im Hub",
            description="Gemeinsamer Familienkalender direkt im Familienhub, zusätzlich zu CalDAV-Kalendern und Kalender-Abos.",
            capabilities=frozenset({"calendar"}),
            builtin=True,
            fallback=True,
        )

    def is_configured(self) -> bool:
        return True
