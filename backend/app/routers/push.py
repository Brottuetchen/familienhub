"""Push-Device-Verwaltung (FCM + Web Push)."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.notification_prefs import NotificationPreference
from app.models.push_device import PushDevice
from app.models.user import User
from app.services.notify import notify

router = APIRouter(prefix="/api/push", tags=["push"])


class RegisterDeviceRequest(BaseModel):
    kind: str  # fcm | webpush
    token: str = None  # FCM token (deprecated, use 'token' field)
    subscription: dict = None  # WebPush subscription object
    device_name: str = None


class NotificationPrefRequest(BaseModel):
    category: str
    enabled: bool = True
    quiet_start: Optional[str] = None  # HH:MM
    quiet_end: Optional[str] = None    # HH:MM


@router.get("/vapid-public-key")
async def vapid_public_key():
    """Öffentlicher VAPID-Schlüssel für Web Push (ohne Anmeldung)."""
    from app.config import settings

    if not (settings.vapid_public_key and settings.vapid_private_key):
        raise HTTPException(501, "Web Push nicht eingerichtet (VAPID-Schlüssel fehlen)")
    return {"publicKey": settings.vapid_public_key}


@router.post("/devices")
async def register_device(
    data: RegisterDeviceRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Registriert ein neues Gerät."""
    if data.kind not in ("fcm", "webpush"):
        raise HTTPException(400, "kind must be fcm or webpush")

    # Token extrahieren (FCM oder WebPush)
    if data.kind == "fcm":
        token = data.token
        if not token:
            raise HTTPException(400, "FCM requires 'token' field")
    else:  # webpush
        import json
        if data.subscription:
            token = json.dumps(data.subscription)
        elif data.token:
            # Fallback: token als JSON-String
            token = data.token
        else:
            raise HTTPException(400, "WebPush requires 'subscription' or 'token' field")

    # Vorhandenes Gerät updaten (Deduplizierung)
    existing = db.query(PushDevice).filter(
        PushDevice.user_id == user.id,
        PushDevice.token == token
    ).first()

    if existing:
        existing.device_name = data.device_name
        db.commit()
        return {"id": existing.id}

    device = PushDevice(
        user_id=user.id,
        kind=data.kind,
        token=token,
        device_name=data.device_name
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return {"id": device.id}


@router.get("/devices")
async def list_devices(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Eigene Geräte."""
    devices = db.query(PushDevice).filter(PushDevice.user_id == user.id).all()
    return [
        {
            "id": d.id,
            "kind": d.kind,
            "device_name": d.device_name,
            "last_seen": d.last_seen.isoformat() if d.last_seen else None
        }
        for d in devices
    ]


@router.delete("/devices/{device_id}")
async def delete_device(
    device_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Löscht eigenes Gerät."""
    device = db.query(PushDevice).filter(
        PushDevice.id == device_id,
        PushDevice.user_id == user.id
    ).first()
    
    if not device:
        raise HTTPException(404, "Device not found")
    
    db.delete(device)
    db.commit()
    return {"success": True}


@router.post("/test")
async def test_push(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Testnachricht an alle eigenen Geräte."""
    result = await notify(
        user.id,
        "Test-Nachricht",
        "Dies ist eine Testnachricht vom Familienhub.",
        data={},
        category="system"
    )
    return result


@router.get("/me/notification-prefs")
async def get_notification_prefs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Eigene Benachrichtigungseinstellungen."""
    prefs = db.query(NotificationPreference).filter(
        NotificationPreference.user_id == user.id
    ).all()

    return [
        {
            "category": p.category,
            "enabled": p.enabled,
            "quiet_start": p.quiet_start.strftime("%H:%M") if p.quiet_start else None,
            "quiet_end": p.quiet_end.strftime("%H:%M") if p.quiet_end else None,
        }
        for p in prefs
    ]


@router.put("/me/notification-prefs")
async def update_notification_prefs(
    prefs: List[NotificationPrefRequest],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Benachrichtigungseinstellungen aktualisieren."""
    from datetime import datetime

    # Alte Einstellungen löschen
    db.query(NotificationPreference).filter(
        NotificationPreference.user_id == user.id
    ).delete()

    # Neue Einstellungen speichern
    for pref_req in prefs:
        quiet_start = None
        quiet_end = None

        if pref_req.quiet_start:
            quiet_start = datetime.strptime(pref_req.quiet_start, "%H:%M").time()
        if pref_req.quiet_end:
            quiet_end = datetime.strptime(pref_req.quiet_end, "%H:%M").time()

        pref = NotificationPreference(
            user_id=user.id,
            category=pref_req.category,
            enabled=pref_req.enabled,
            quiet_start=quiet_start,
            quiet_end=quiet_end,
        )
        db.add(pref)

    db.commit()
    return {"success": True}
