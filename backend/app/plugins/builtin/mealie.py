from app.plugins.base import Plugin, Setting


class MealiePlugin(Plugin):
    """Mealie: recipes, household meal plan and shopping list."""

    def __init__(self):
        super().__init__(
            id="mealie",
            name="Mealie",
            description="Rezepte aus Mealie suchen und einplanen, Mealie-Essensplan im Wochenplan, Mealie-Einkaufsliste als Einkaufsquelle.",
            capabilities=frozenset({"meal_planning", "meal_source", "shopping"}),
            settings=(
                Setting("MEALIE_URL", "Adresse (vom Server aus erreichbar)", help="z. B. http://mealie.lan:9000"),
                Setting("MEALIE_TOKEN", "API-Token", secret=True,
                        help="In Mealie: Profil → API-Tokens → neues Token"),
                Setting("MEALIE_PUBLIC_URL", "Adresse für Links in der App", required=False,
                        help="Zum Öffnen von Rezepten im Browser; leer = wie oben"),
                Setting("MEALIE_SHOPPING_LIST", "Name der Einkaufsliste", required=False,
                        help="Leer = die erste Liste in Mealie"),
            ),
            builtin=True,
        )
