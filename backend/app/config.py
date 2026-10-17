"""Zentrale Konfiguration des Familienhubs.

Alle Einstellungen werden aus Umgebungsvariablen (oder einer ``.env`` Datei)
gelesen. Es werden bewusst KEINE Secrets im Code hinterlegt. Jeder Connector
ist optional: Fehlt die Konfiguration, läuft der Hub ohne diesen Baustein und der
betreffende Baustein liefert leere/Beispiel-Daten statt einen Fehler zu werfen.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo-Wurzel (…/config.py -> app -> backend -> root), damit die .env unabhängig
# vom Arbeitsverzeichnis gefunden wird (der Installer schreibt sie in die Wurzel).
_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Applikationsweite Einstellungen (env-driven).

    Kern-Einstellungen stehen hier. Plugins lesen ihre Werte über
    ``app.plugins.base.get_setting`` (diese Klasse, Admin-Overrides oder Umgebung).
    """

    model_config = SettingsConfigDict(
        env_file=(str(_ROOT / ".env"), str(_ROOT / "backend" / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App / Server ---
    app_name: str = Field(default="Familienhub")
    environment: str = Field(default="development")  # development | production
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    timezone: str = "Europe/Berlin"

    # TLS-Verifikation für ausgehende Requests (selbst-signierte Zertifikate: false)
    verify_tls: bool = True
    connector_timeout: float = 6.0

    # --- Plugins ---
    # Kommagetrennte Plugin-IDs, die trotz Konfiguration aus bleiben sollen (z. B. "weather")
    plugins_disabled: str = ""

    # --- Security / Auth ---
    secret_key: str = Field(default="CHANGE_ME_dev_only_secret_key")
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    secure_cookies: bool = False
    cors_origins: str = "*"

    # --- OIDC (z. B. Authentik) ---
    oidc_issuer: Optional[str] = None
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[str] = None
    oidc_redirect_uri_web: Optional[str] = None
    oidc_redirect_uri_app: Optional[str] = None
    oidc_auto_create: bool = False

    # --- Datenbank ---
    database_url: str = "sqlite:///./familienhub.db"

    # --- Push: Web Push (VAPID) und Firebase (FCM) ---
    vapid_private_key: Optional[str] = None
    vapid_public_key: Optional[str] = None
    vapid_email: str = "mailto:admin@example.com"
    fcm_service_account_file: Optional[str] = None
    fcm_project_id: Optional[str] = None

    # Verzeichnis mit App-Downloads (APK + index.html), ausgeliefert unter /downloads/
    downloads_dir: Optional[str] = None

    # --- Plugin: Wetter (Open-Meteo, kein Key nötig) ---
    weather_enabled: bool = True
    weather_latitude: float = 52.52
    weather_longitude: float = 13.405
    weather_location_name: str = "Zuhause"

    # --- Plugin: Habitica (optionale Konten pro Nutzer) ---
    habitica_url: str = ""

    # --- Plugin: Nextcloud (Aufgaben + Kalender; Konten pro Nutzer, global optional) ---
    caldav_url: Optional[str] = None
    caldav_username: Optional[str] = None
    caldav_password: Optional[str] = None

    # --- Plugin: Home Assistant (Einkauf, Cookidoo-Essensplan, Haus-Karte) ---
    homeassistant_url: Optional[str] = None
    homeassistant_token: Optional[str] = None
    ha_mealplan_calendar: str = "calendar.cookidoo_speiseplan"
    ha_shopping_todo: str = "todo.einkaufsliste"
    ha_recipe_shopping_todo: str = "todo.cookidoo_einkaufsliste"
    ha_house_entities: str = ""  # Haus-Karte: geordnete, kommagetrennte Entitäts-IDs
    ha_house_write_entities: str = ""  # Separat freigegebene Aktionen; Lesen erteilt kein Schreibrecht

    # --- Plugin: Shelfarr (Bücher/Hörbücher) ---
    shelfarr_url: Optional[str] = None
    shelfarr_token: Optional[str] = None
    shelfarr_language: str = "de"
    shelfarr_user_map: Optional[str] = None  # "hubname=shelfarrname,…"; Standard: gleicher Name

    @property
    def cors_origin_list(self) -> List[str]:
        """CORS Origins als Liste (kommasepariert in der ENV)."""
        raw = (self.cors_origins or "").strip()
        if raw in ("", "*"):
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def disabled_plugins(self) -> List[str]:
        return [p.strip() for p in (self.plugins_disabled or "").split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    """Gecachte Settings-Instanz (Singleton)."""
    return Settings()


settings = get_settings()
