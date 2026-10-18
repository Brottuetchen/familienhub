from typing import Optional

from app.plugins.base import Plugin, Setting


class IcsPlugin(Plugin):
    """Read-only calendar subscriptions: school holidays, waste collection, club dates."""

    def __init__(self):
        super().__init__(
            id="ics",
            name="Kalender-Abos (ICS)",
            description="Schulferien, Müllabfuhr, Vereinstermine: abonnierte Kalender erscheinen im Familienkalender (nur lesen).",
            capabilities=frozenset({"calendar"}),
            settings=(
                Setting("ICS_FEEDS", "Abonnierte Kalender",
                        help="Je Kalender „Name | https://…/kalender.ics“, mehrere durch ; getrennt"),
            ),
            builtin=True,
        )

    def health_url(self) -> Optional[str]:
        from app.plugins.base import get_setting
        from app.services.ics import parse_feeds

        feeds = parse_feeds(get_setting("ICS_FEEDS"))
        return feeds[0][1] if feeds else None
