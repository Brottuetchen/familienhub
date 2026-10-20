"""Zentrale Konfiguration des Familienhubs.

Alle Einstellungen werden aus Umgebungsvariablen (oder einer ``.env`` Datei)
gelesen. Es werden bewusst KEINE Secrets im Code hinterlegt. Jeder Connector
ist optional: Fehlt die Konfiguration, läuft der Hub ohne diesen Baustein und der
betreffende Baustein liefert leere/Beispiel-Daten statt einen Fehler zu werfen.
"""

from __future__ import annotations

import logging
import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo-Wurzel (…/config.py -> app -> backend -> root), damit die .env unabhängig
# vom Arbeitsverzeichnis gefunden wird (der Installer schreibt sie in die Wurzel).
_ROOT = Path(__file__).resolve().parents[2]

PLACEHOLDER_SECRET_KEY = "CHANGE_ME_dev_only_secret_key"
SECRET_KEY_FILENAME = "secret_key"

_log = logging.getLogger("familienhub.config")


def load_or_create_secret_key(data_dir: str) -> Optional[str]:
    """Read ``<data_dir>/secret_key``; create it (mode 0600, atomically) if missing.

    Returns None if the directory is not usable. The key is never logged.
    """
    path = Path(data_dir) / SECRET_KEY_FILENAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            fd = None
        if fd is not None:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(secrets.token_urlsafe(48))
        value = path.read_text(encoding="utf-8").strip()
        return value or None
    except OSError as exc:
        _log.error(
            "SECRET_KEY is not set and %s is not usable (%s). Mount a writable volume at DATA_DIR "
            "or set SECRET_KEY explicitly.", path, exc.__class__.__name__,
        )
        return None


VAPID_FILENAME = "vapid.json"


def load_or_create_vapid_keys(data_dir: str) -> Optional[tuple[str, str]]:
    """Read ``<data_dir>/vapid.json`` (private, public; base64url); create it (0600) if missing.

    Lets Web Push work without configuration. Returns None if the directory is not usable.
    """
    import json

    path = Path(data_dir) / VAPID_FILENAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            fd = None
        if fd is not None:
            from scripts.generate_vapid import generate_keys

            private, public = generate_keys()
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"private": private, "public": public}, fh)
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("private") and data.get("public"):
            return data["private"], data["public"]
        return None
    except (OSError, ValueError, ImportError) as exc:
        _log.error("Web Push keys could not be created in %s (%s). Set VAPID_PRIVATE_KEY and "
                   "VAPID_PUBLIC_KEY, or mount a writable volume at DATA_DIR.", path, exc.__class__.__name__)
        return None


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
    host: str = "0.0.0.0"  # nosec B104 – im Container gewollt; erreichbar nur über Docker-Port/Reverse-Proxy
    port: int = 8000
    log_level: str = "info"
    timezone: str = "Europe/Berlin"

    # TLS-Verifikation für ausgehende Requests (selbst-signierte Zertifikate: false)
    verify_tls: bool = True
    connector_timeout: float = 6.0

    # --- Plugins ---
    # Kommagetrennte Plugin-IDs, die trotz Konfiguration aus bleiben sollen (z. B. "weather")
    plugins_disabled: str = ""
    # Install plugins from GitHub in the app (Administration → Plugins & access). Set false to turn the
    # installer off; plugins that are already installed keep loading.
    plugin_install_enabled: bool = True
    # Extra arguments for pip when a plugin is installed, e.g. "--index-url https://pypi.example.org/simple"
    plugin_pip_args: str = ""
    # Official plugin and theme store (docs/store.md): an index.json maintained by the project. Empty switches the
    # official source off (admins can still add their own GitHub repos as extra sources).
    store_index_url: str = "https://raw.githubusercontent.com/brottuetchen/familienhub-store/main/index.json"
    store_cache_seconds: int = 300  # how long a fetched index is reused

    # --- Security / Auth ---
    # Empty or placeholder: loaded from / generated into <DATA_DIR>/secret_key (see _resolve_secret_key)
    secret_key: str = Field(default=PLACEHOLDER_SECRET_KEY)
    data_dir: str = "/app/data"  # persistent state of the hub itself (generated secret key)
    # Setup code (shown in the server log) is optional; set true if the hub is reachable from the
    # internet before the first admin exists.
    setup_require_code: bool = False
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    secure_cookies: bool = False
    # Sub-path hosting (docs/home-assistant.md). ROOT_PATH: fixed prefix such as /hub. TRUST_INGRESS_HEADER: honour
    # Home Assistant's X-Ingress-Path, but only from INGRESS_PROXY_IPS (the ingress gateway).
    root_path: str = ""
    trust_ingress_header: bool = False
    ingress_proxy_ips: str = "172.30.32.2"
    cors_origins: str = ""  # leer = nur gleiche Herkunft; "*" erlaubt alle, dann aber ohne Anmelde-Cookies

    # --- OIDC (z. B. Authentik) ---
    oidc_issuer: Optional[str] = None
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[str] = None
    oidc_redirect_uri_web: Optional[str] = None
    oidc_redirect_uri_app: Optional[str] = None
    oidc_auto_create: bool = False

    # --- Datenbank ---
    database_url: str = "sqlite:///./familienhub.db"

    # --- Backups (Administration → Backup) and update notice ---
    backup_auto: bool = False  # nightly backup into <DATA_DIR>/backups
    backup_keep: int = 7  # automatic backups to keep
    update_check: bool = True  # look for a newer release on GitHub (cached, a few times a day)
    update_check_repo: str = "Brottuetchen/familienhub"  # owner/name whose releases are checked

    # --- Push: Web Push (VAPID) und Firebase (FCM) ---
    vapid_private_key: Optional[str] = None
    vapid_public_key: Optional[str] = None
    vapid_email: str = ""  # empty: the first admin's email (see services/notify.vapid_contact)
    # Without VAPID_PRIVATE_KEY/VAPID_PUBLIC_KEY: generate them once into <DATA_DIR>/vapid.json
    vapid_auto: bool = True
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

    @model_validator(mode="after")
    def _resolve_secret_key(self) -> "Settings":
        if not self.secret_key.strip() or self.secret_key == PLACEHOLDER_SECRET_KEY:
            loaded = load_or_create_secret_key(self.data_dir)
            if loaded:
                self.secret_key = loaded
            elif not self.secret_key.strip():
                self.secret_key = PLACEHOLDER_SECRET_KEY
        if self.vapid_auto and not (self.vapid_private_key or self.vapid_public_key):
            keys = load_or_create_vapid_keys(self.data_dir)
            if keys:
                self.vapid_private_key, self.vapid_public_key = keys
        return self

    @property
    def cors_origin_list(self) -> List[str]:
        """CORS Origins als Liste (kommasepariert in der ENV)."""
        raw = (self.cors_origins or "").strip()
        if raw == "":
            return []
        if raw == "*":
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
