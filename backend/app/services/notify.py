"""Unified Push-Benachrichtigungsdienst (FCM + Web Push).

WP 4 – notify()-Funktion mit Ruhezeiten und Kategoriefiltern.
"""

import json
from datetime import datetime, time
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging_config import get_logger
from app.models.notification_prefs import NotificationPreference
from app.models.push_device import PushDevice

logger = get_logger("service.notify")

try:
    from pywebpush import WebPushException, webpush
except ImportError:
    webpush = WebPushException = None

try:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    import httpx
    _fcm_available = True
except ImportError:
    _fcm_available = False


class NotifyService:
    """Push-Service mit Ruhezeiten und Kategoriefiltern."""

    def __init__(self):
        self._fcm_creds = None

    @property
    def webpush_configured(self) -> bool:
        return bool(settings.vapid_private_key and settings.vapid_public_key and webpush)

    @property
    def fcm_configured(self) -> bool:
        return bool(settings.fcm_service_account_file and settings.fcm_project_id and _fcm_available)

    def _get_fcm_token(self) -> Optional[str]:
        """Holt FCM-Access-Token (gecacht, 1h gültig)."""
        if not self.fcm_configured:
            return None
        try:
            if not self._fcm_creds:
                self._fcm_creds = service_account.Credentials.from_service_account_file(
                    settings.fcm_service_account_file,
                    scopes=["https://www.googleapis.com/auth/firebase.messaging"]
                )
            self._fcm_creds.refresh(Request())
            return self._fcm_creds.token
        except Exception as e:
            # Nur die Fehlerart loggen: Meldungen der Google-Bibliothek können Zugangsdaten enthalten
            logger.warning("FCM-Zugang konnte nicht erneuert werden (%s)", type(e).__name__)
            return None

    def _is_in_quiet_hours(self, quiet_start: Optional[time], quiet_end: Optional[time]) -> bool:
        """Prüft, ob aktuelle Zeit in Ruhezeiten liegt."""
        if not quiet_start or not quiet_end:
            return False

        now_time = datetime.now().time()

        # Ruhezeit über Mitternacht (z.B. 22:00–08:00)
        if quiet_start > quiet_end:
            return now_time >= quiet_start or now_time <= quiet_end
        else:
            return quiet_start <= now_time <= quiet_end

    def _should_suppress(self, db: Session, user_id: int, category: str) -> bool:
        """Prüft, ob Benachrichtigung unterdrückt werden soll."""
        # Kategoriespezifische Einstellung
        pref = db.query(NotificationPreference).filter(
            NotificationPreference.user_id == user_id,
            NotificationPreference.category == category
        ).first()

        if pref:
            if not pref.enabled:
                return True
            if self._is_in_quiet_hours(pref.quiet_start, pref.quiet_end):
                return True

        # Fallback auf "all"-Kategorie
        all_pref = db.query(NotificationPreference).filter(
            NotificationPreference.user_id == user_id,
            NotificationPreference.category == "all"
        ).first()

        if all_pref:
            if not all_pref.enabled:
                return True
            if self._is_in_quiet_hours(all_pref.quiet_start, all_pref.quiet_end):
                return True

        return False

    async def _send_webpush(self, db: Session, device: PushDevice, title: str, body: str, data: dict, category: str) -> bool:
        """Sendet Web Push an ein Gerät."""
        try:
            sub_info = json.loads(device.token)
            payload = json.dumps({"title": title, "body": body, "data": data or {}, "category": category})
            webpush(
                subscription_info=sub_info,
                data=payload,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": vapid_contact(db)},
                ttl=86400
            )
            return True
        except WebPushException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):
                db.delete(device)
                db.commit()
                logger.info("removed stale webpush device %s", device.id)
            else:
                logger.warning("webpush send error: %s", e, exc_info=True)
            return False
        except Exception as e:
            logger.warning("webpush send error: %s", e, exc_info=True)
            return False

    async def _send_fcm(self, db: Session, device: PushDevice, title: str, body: str, data: dict, category: str) -> bool:
        """Sendet FCM an ein Gerät."""
        token = self._get_fcm_token()
        if not token:
            return False

        try:
            async with httpx.AsyncClient() as client:
                # Alle data-Felder müssen Strings sein
                str_data = {k: str(v) for k, v in (data or {}).items()}
                str_data["category"] = category

                resp = await client.post(
                    f"https://fcm.googleapis.com/v1/projects/{settings.fcm_project_id}/messages:send",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json={"message": fcm_message(device.token, title, body, str_data, category)},
                    timeout=10
                )
                if resp.status_code == 200:
                    return True

                # UNREGISTERED = ungültiges Token
                if resp.status_code == 404 or "UNREGISTERED" in resp.text:
                    db.delete(device)
                    db.commit()
                    logger.info("removed stale fcm device %s", device.id)
                else:
                    logger.warning("fcm send failed: %d %s", resp.status_code, resp.text)
                return False
        except Exception as e:
            logger.warning("fcm send error: %s", e, exc_info=True)
            return False


def vapid_contact(db: Session) -> str:
    """Contact for push services: VAPID_EMAIL if set to a real address, else the first admin's email.

    The admin enters the email during setup, so a zero-config hub still sends a real contact.
    """
    configured = (settings.vapid_email or "").strip()
    if configured and "example." not in configured:
        return configured if configured.startswith(("mailto:", "https:")) else f"mailto:{configured}"
    from app.models.user import ROLE_ADMIN, User

    admin = (db.query(User).filter(User.role == ROLE_ADMIN, User.is_active == True)  # noqa: E712
             .order_by(User.id).first())
    if admin and admin.email and "@" in admin.email:
        return f"mailto:{admin.email}"
    return configured or "mailto:admin@example.org"


def fcm_message(token: str, title: str, body: str, data: dict, category: str) -> dict:
    """FCM-Nachricht. Mit Knöpfen („actions“) als reine Datennachricht: Android zeigt
    Benachrichtigungen mit „notification“-Block selbst an – ohne Knöpfe. Die App
    stellt Datennachrichten auch im Hintergrund dar, dann mit Knöpfen."""
    if data.get("actions"):
        return {"token": token, "data": {**data, "title": title, "body": body or ""},
                "android": {"priority": "HIGH"}}
    return {"token": token, "notification": {"title": title, "body": body}, "data": data,
            "android": {"priority": "HIGH", "notification": {"channel_id": category}}}


_notify_service = NotifyService()


# Kategorien, die Push-Mitteilungen haben können (App: Kanäle und Einstellungen)
CATEGORIES = ("task_assigned", "task_due", "reminder", "shopping", "house", "media", "documents", "stars", "system")


async def notify(
    user_id: int,
    title: str,
    body: str,
    data: dict = None,
    category: str = "info",
    source: str = "hub",
    silent: bool = False,
) -> int:
    """Mitteilung an eine Person: Verlauf + Push an alle ihre Geräte.

    Der Eintrag im Verlauf entsteht immer; der Push entfällt bei Ruhezeit oder
    abgeschalteter Kategorie.

    Returns:
        Anzahl erfolgreich erreichter Geräte
    """
    from app.core.database import SessionLocal
    from app.models.notification_log import NotificationLog

    db = SessionLocal()
    try:
        from app.core.i18n import translate
        from app.models.user import User

        recipient = db.get(User, user_id)
        lang = getattr(recipient, "language", None)
        title, body = translate(title, lang), translate(body, lang)  # in the recipient's language (#24)
        entry = NotificationLog(
            user_id=user_id, title=title, body=body or "", category=category or "system",
            route=(data or {}).get("route"), source=source, delivered=0, suppressed=False,
        )
        db.add(entry)
        db.commit()
        data = {**(data or {}), "notification_id": entry.id}

        if silent:  # nur Verlauf (z. B. wenn das Quellsystem selbst schon pusht)
            entry.suppressed = True
            db.commit()
            return 0

        if _notify_service._should_suppress(db, user_id, category):
            logger.debug("notification suppressed for user %d category %s", user_id, category)
            entry.suppressed = True
            db.commit()
            return 0

        devices = db.query(PushDevice).filter(PushDevice.user_id == user_id).all()
        success = 0
        for device in list(devices):
            ok = False
            if device.kind == "webpush" and _notify_service.webpush_configured:
                ok = await _notify_service._send_webpush(db, device, title, body, data, category)
            elif device.kind == "fcm" and _notify_service.fcm_configured:
                ok = await _notify_service._send_fcm(db, device, title, body, data, category)
            if ok:
                success += 1

        from app.models.ntfy import NtfyTarget
        from app.services import ntfy

        target = db.get(NtfyTarget, user_id)
        if target is not None and target.enabled and await ntfy.publish(target.topic, title, body, data, category):
            success += 1

        entry.delivered = success
        db.commit()
        return success
    finally:
        db.close()
