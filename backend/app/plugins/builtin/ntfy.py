from typing import Optional

from app.plugins.base import Plugin, Setting, get_setting


class NtfyPlugin(Plugin):
    """Push via ntfy: each person subscribes to their own secret topic (e.g. in the ntfy iOS app)."""

    def __init__(self):
        super().__init__(
            id="ntfy",
            name="ntfy",
            description="Push-Mitteilungen über ntfy – z. B. für iPhones ohne App-Store-App. Jede Person abonniert ihr eigenes geheimes Topic.",
            capabilities=frozenset({"push_ntfy"}),
            settings=(
                Setting("NTFY_URL", "ntfy-Server", help="z. B. https://ntfy.sh oder der eigene Server"),
                Setting("NTFY_TOKEN", "Zugangs-Token zum Senden", secret=True, required=False,
                        help="Nur nötig, wenn der Server anonymes Senden verbietet (Token mit Schreibrecht auf fh_*)"),
                Setting("HUB_PUBLIC_URL", "Adresse des Hubs für Links und Knöpfe", required=False,
                        help="Von unterwegs erreichbar, z. B. https://hub.example.org; leer = keine Knöpfe"),
            ),
            builtin=True,
        )

    def health_url(self) -> Optional[str]:
        url = get_setting("NTFY_URL")
        return f"{str(url).rstrip('/')}/v1/health" if url else None
