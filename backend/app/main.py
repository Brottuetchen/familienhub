"""Familienhub – FastAPI-Anwendung.

Assembliert alle Router, Middleware und das statische Frontend (PWA).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import settings
from app.core.database import init_db, redact_db_url
from app.core.logging_config import get_logger, setup_logging
from app.services.scheduler import run_scheduler
from app.plugins.registry import plugin_registry
from app.routers import (
    admin,
    admin_panel,
    feedback,
    invites,
    setup,
    auth,
    calendar,
    health,
    meals,
    modules,
    notifications,
    ntfy,
    plugins as plugins_router,
    profile,
    recipe_sources,
    push,
    recipes,
    reminders,
    tasks,
    themes,
    today,
)

setup_logging()
logger = get_logger("familienhub")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("%s v%s starting (%s)", settings.app_name, __version__, settings.environment)
    init_db()
    logger.info("Database initialized: %s", redact_db_url(settings.database_url))
    # Admin-editierbare Laufzeit-Overrides (Connector-Zugänge) anwenden.
    from app.core.database import SessionLocal
    from app.services.config_store import apply_overrides

    _cfg_db = SessionLocal()
    try:
        apply_overrides(_cfg_db)
    finally:
        _cfg_db.close()
    # Plugins an admin installed from GitHub: a broken one is logged and skipped, the hub keeps running
    from app.plugins import installer

    installer.load_installed(app)
    logger.info("Plugins aktiv: %s", ", ".join(p.id for p in plugin_registry.all() if p.active) or "keine")
    # Ersteinrichtung: ohne Admin einen Einrichtungscode ins Log schreiben (#4)
    from app.services import setup as setup_service

    _setup_db = SessionLocal()
    try:
        setup_service.prepare(_setup_db)
    finally:
        _setup_db.close()
    if settings.secret_key == "CHANGE_ME_dev_only_secret_key" or len(settings.secret_key.encode()) < 32:
        if settings.is_production:
            # Mit bekanntem oder kurzem Schlüssel ließen sich Anmelde-Tokens fälschen: im Betrieb nicht starten
            raise RuntimeError("SECRET_KEY fehlt oder ist zu kurz (mindestens 32 Zeichen) – siehe .env.example")
        logger.warning("SECRET_KEY is default or short – set a strong SECRET_KEY in production!")
    logger.info("=" * 60)

    # Hintergrund-Scheduler (fällige Erinnerungen -> Push)
    scheduler_task = asyncio.create_task(run_scheduler())
    try:
        yield
    finally:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title=f"{settings.app_name} API",
    description=(
        "Familienhub – Termine, Aufgaben, Einkauf, Essen und Erinnerungen für die "
        "Familie, erweiterbar über Plugins."
    ),
    version=__version__,
    lifespan=lifespan,
    # API-Doku nur außerhalb des Betriebs (sie verrät alle Endpunkte)
    docs_url=None if settings.is_production and not settings.debug else "/docs",
    redoc_url=None if settings.is_production and not settings.debug else "/redoc",
    openapi_url=None if settings.is_production and not settings.debug else "/openapi.json",
)

# Error and status texts in the client's language (#24); added before CORS so CORS stays outermost
from app.core import i18n  # noqa: E402

i18n.install(app)

if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        # "*" nie zusammen mit Anmelde-Cookies: Starlette würde sonst jede fremde Herkunft zurückspiegeln
        allow_credentials=settings.cors_origin_list != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Content-Security-Policy": "frame-ancestors 'none'; object-src 'none'; base-uri 'self'",
}


MAX_BODY_BYTES = 2 * 1024 * 1024  # größte erlaubte Nutzlast: Profilbild 512 KB (Base64 ≈ 700 KB)


@app.middleware("http")
async def limit_body_size(request, call_next):
    """Übergroße Anfragen früh ablehnen, bevor sie eingelesen werden (auch an öffentlichen Endpunkten)."""
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
        from fastapi.responses import JSONResponse

        return JSONResponse({"detail": "Anfrage zu groß"}, status_code=413)
    return await call_next(request)


@app.middleware("http")
async def security_headers(request, call_next):
    """Schutz gegen Einbetten (Clickjacking), MIME-Raten und Referrer-Lecks. Eigene Header einer Antwort bleiben."""
    response = await call_next(request)
    for key, value in SECURITY_HEADERS.items():
        response.headers.setdefault(key, value)
    return response


@app.middleware("http")
async def drop_read_caches_after_changes(request, call_next):
    """Safety net for the short CalDAV read cache: any changing request drops it (connector writes do too).

    Account or list setup changes also forget the cached client and calendar list.
    """
    response = await call_next(request)
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.url.path.startswith("/api/"):
        from app.services import caldav_cache

        caldav_cache.clear_reads()
        if request.url.path.endswith(("/me/caldav", "/me/task-lists")) or "/caldav" in request.url.path:
            caldav_cache.invalidate_account()
    return response


@app.middleware("http")
async def refresh_after_changes(request, call_next):
    """Nach erfolgreichen Änderungen an Einkauf/Aufgaben/Essen/Erinnerungen: Geräte stumm neu laden lassen."""
    response = await call_next(request)
    from app.services import refresh

    scope = refresh.scope_for(request.method, request.url.path, response.status_code)
    if scope:
        refresh.schedule_refresh(scope)
    return response


# Kern-Router; Integrationen bringen ihre Router als Plugin mit
for module in (health, auth, calendar, modules, notifications, today, tasks, reminders, meals, recipes, push, themes, profile, admin,
               admin_panel, feedback, invites, setup, ntfy, recipe_sources, plugins_router):
    app.include_router(module.router)
plugin_registry.include_routers(app)


# --- Statisches Frontend (Flutter-Web-App) ---
# WICHTIG: Muss NACH allen API-Routern gemountet werden.
# Im Docker-Image liegt hier der Flutter-Web-Build (app/build/web), siehe backend/Dockerfile.
_public_dir = Path(__file__).resolve().parent.parent.parent / "public"


def mount_frontend(target: FastAPI, directory: Path) -> bool:
    """Liefert die Web-App aus. index.html und manifest.json mit APP_NAME, ohne Cache."""
    import html
    import json

    from fastapi.responses import HTMLResponse, JSONResponse

    if not (directory / "index.html").exists():
        return False
    no_cache = {"Cache-Control": "no-cache"}

    @target.get("/", response_class=HTMLResponse, include_in_schema=False)
    @target.get("/index.html", response_class=HTMLResponse, include_in_schema=False)
    async def serve_index():
        content = (directory / "index.html").read_text(encoding="utf-8")
        name = html.escape(settings.app_name)
        content = content.replace("<title>Familienhub</title>", f"<title>{name}</title>")
        content = content.replace('content="Familienhub"', f'content="{name}"')
        return HTMLResponse(content=content, headers=no_cache)

    @target.get("/manifest.json", response_class=JSONResponse, include_in_schema=False)
    async def serve_manifest():
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        manifest["name"] = manifest["short_name"] = settings.app_name
        return JSONResponse(content=manifest, headers=no_cache)

    @target.get("/push-sw.js", include_in_schema=False)
    async def serve_push_worker():
        from fastapi.responses import FileResponse

        # Service Worker nie aus dem Cache, sonst kommen Änderungen nicht an
        return FileResponse(directory / "push-sw.js", media_type="text/javascript", headers=no_cache)

    target.mount("/", StaticFiles(directory=str(directory), html=False), name="frontend")
    return True


def mount_downloads(target: FastAPI, directory: Optional[str]) -> bool:
    """App-Downloads (APK) unter /downloads/, nur wenn DOWNLOADS_DIR gesetzt ist und existiert."""
    if not directory or not Path(directory).is_dir():
        return False
    import mimetypes

    # Schlanke Images kennen .apk nicht → sonst text/plain, Android lädt dann nicht als App
    mimetypes.add_type("application/vnd.android.package-archive", ".apk")
    target.mount("/downloads", StaticFiles(directory=directory, html=True), name="downloads")
    return True


mount_downloads(app, settings.downloads_dir)  # vor "/" mounten, sonst greift das Frontend

if mount_frontend(app, _public_dir):
    logger.info("Serving frontend from %s", _public_dir)
else:
    logger.warning("Frontend directory not found: %s", _public_dir)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port, log_level=settings.log_level)
