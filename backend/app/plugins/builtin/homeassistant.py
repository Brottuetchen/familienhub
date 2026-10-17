from app.plugins.base import Plugin, Setting


class HomeAssistantPlugin(Plugin):
    """Einkaufsliste, Cookidoo-Essensplan und ausgewählte Haus-Zustände."""

    def __init__(self):
        super().__init__(
            id="homeassistant",
            name="Home Assistant",
            description="Einkaufsliste, Cookidoo-Wochenplan und Haus-Zustände über Home Assistant.",
            capabilities=frozenset({"shopping", "meal_source"}),
            settings=(
                Setting("HOMEASSISTANT_URL", "Adresse", help="z. B. http://homeassistant.local:8123"),
                Setting("HOMEASSISTANT_TOKEN", "Langlebiges Zugangstoken", secret=True),
                Setting("HA_SHOPPING_TODO", "Einkaufsliste (todo-Entität)", required=False, help="Standard: todo.einkaufsliste"),
                Setting("HA_RECIPE_SHOPPING_TODO", "Rezept-Zutaten (todo-Entität)", required=False,
                        help="Standard: todo.cookidoo_einkaufsliste"),
                Setting("HA_MEALPLAN_CALENDAR", "Essensplan (calendar-Entität)", required=False,
                        help="Standard: calendar.cookidoo_speiseplan"),
                Setting("HA_HOUSE_WRITE_ENTITIES", "Haussteuerung: Schreibfreigabe", required=False,
                        help="Bis zu 6 light/switch/script/scene-IDs; leer = keine Aktionen. Unabhängig von Leseauswahl."),
                Setting("HA_HOUSE_ENTITIES", "Haus-Karte in Heute", required=False,
                        help="Bis zu 6 Entitäts-IDs, kommagetrennt in Anzeigereihenfolge; leer = ausgeblendet."),
            ),
            builtin=True,
        )

    def routers(self):
        from app.routers import house, shopping

        return [shopping.router, house.router]
