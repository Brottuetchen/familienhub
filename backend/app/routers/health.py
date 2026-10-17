"""System-Health & Meta-Informationen (ohne Anmeldung)."""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.config import settings
from app.plugins.registry import plugin_registry

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
async def health():
    from app.services.notify import NotifyService

    push = NotifyService()
    return {
        "status": "online",
        "app": settings.app_name,
        "version": __version__,
        "environment": settings.environment,
        "features": {
            "oidc": bool(settings.oidc_issuer and settings.oidc_client_id),
            "push": push.fcm_configured or push.webpush_configured,
            "fcm": push.fcm_configured,
            "webpush": push.webpush_configured,
        },
        "plugins": [p.id for p in plugin_registry.all() if p.active],
    }
