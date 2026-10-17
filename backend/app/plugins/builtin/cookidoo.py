from app.plugins.base import Plugin, Setting


class CookidooPlugin(Plugin):
    """Rezepte aus Cookidoo suchen und in den Wochenplan legen (cookidoo-api)."""

    def __init__(self):
        super().__init__(
            id="cookidoo",
            name="Cookidoo",
            description="Rezepte suchen, auf Tage legen und Zutaten auf die Cookidoo-Einkaufsliste setzen.",
            capabilities=frozenset({"meal_planning"}),
            settings=(
                Setting("COOKIDOO_EMAIL", "E-Mail des Cookidoo-Kontos"),
                Setting("COOKIDOO_PASSWORD", "Passwort", secret=True),
                Setting("COOKIDOO_COUNTRY", "Land", required=False, help="Standard: de"),
                Setting("COOKIDOO_LANGUAGE", "Sprache", required=False, help="Standard: de-DE"),
            ),
            builtin=True,
        )

    def routers(self):
        from app.routers import cookidoo

        return [cookidoo.router]
