"""Tests für Push-Benachrichtigungen (FCM + Web Push).

WP 4 – Tests gemäß BUILD_PROMPT.md Teil C.
"""

import json
from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.push_device import PushDevice
from app.models.user import User


@pytest.fixture
def db() -> Session:
    """Erzeugt eine frische DB-Session für jeden Test."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def user_a(db: Session) -> User:
    """Erstellt Testnutzer A."""
    user = db.query(User).filter(User.username == "user_a").first()
    if not user:
        user = User(
            username="user_a",
            email="a@test.de",
            hashed_password=get_password_hash("test123"),
            full_name="User A",
            role="partner",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@pytest.fixture
def user_b(db: Session) -> User:
    """Erstellt Testnutzer B."""
    user = db.query(User).filter(User.username == "user_b").first()
    if not user:
        user = User(
            username="user_b",
            email="b@test.de",
            hashed_password=get_password_hash("test123"),
            full_name="User B",
            role="partner",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def test_register_fcm_device_dedup(client, admin_token, db):
    """Ein bekanntes FCM-Token wird aktualisiert statt dupliziert."""
    auth = {"Authorization": f"Bearer {admin_token}"}

    # Erstes Gerät registrieren
    resp1 = client.post(
        "/api/push/devices",
        json={"kind": "fcm", "token": "fcm_token_123", "device_name": "Pixel 1"},
        headers=auth,
    )
    assert resp1.status_code == 200
    device_id = resp1.json()["id"]

    # Gleiches Token erneut registrieren mit neuem Namen
    resp2 = client.post(
        "/api/push/devices",
        json={"kind": "fcm", "token": "fcm_token_123", "device_name": "Pixel 1 Updated"},
        headers=auth,
    )
    assert resp2.status_code == 200
    assert resp2.json()["id"] == device_id  # Gleiche ID

    # Prüfen: nur ein Gerät in der DB
    devices = db.query(PushDevice).filter(PushDevice.token == "fcm_token_123").all()
    assert len(devices) == 1
    assert devices[0].device_name == "Pixel 1 Updated"


def test_notify_sends_to_all_devices_of_user(db, user_a):
    """notify() sendet an alle Geräte eines Nutzers."""
    from app.services.notify import notify

    # Drei Geräte für user_a registrieren
    for i in range(3):
        device = PushDevice(
            user_id=user_a.id,
            kind="fcm",
            token=f"token_{i}",
            device_name=f"Device {i}",
        )
        db.add(device)
    db.commit()

    # Mock für FCM-Sendevorgang
    with patch("app.services.notify.NotifyService._send_fcm", new_callable=AsyncMock) as mock_fcm:
        mock_fcm.return_value = True

        with patch("app.services.notify.NotifyService.fcm_configured", True):
            import asyncio
            result = asyncio.run(notify(user_a.id, "Test", "Body", {}, "test"))

    # Alle drei Geräte wurden angesprochen
    assert result == 3
    assert mock_fcm.call_count == 3


def test_fcm_unregistered_deletes_device(db, user_a):
    """FCM 404 oder UNREGISTERED löscht das Gerät aus der DB."""
    from app.services.notify import notify

    device = PushDevice(
        user_id=user_a.id,
        kind="fcm",
        token="invalid_token",
        device_name="Old Device",
    )
    db.add(device)
    db.commit()
    device_id = device.id

    # Mock: FCM antwortet mit 404
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = "Not Found"

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        with patch("app.services.notify.NotifyService.fcm_configured", True):
            with patch("app.services.notify.NotifyService._get_fcm_token", return_value="mock_token"):
                import asyncio
                asyncio.run(notify(user_a.id, "Test", "Body", {}, "test"))

    # Gerät wurde gelöscht
    db.expire_all()
    assert db.query(PushDevice).filter(PushDevice.id == device_id).first() is None


def test_webpush_410_deletes_device(db, user_a, monkeypatch):
    """Web Push 410 (Gone) löscht das Gerät."""
    from app.services.notify import notify
    from app.config import settings

    # VAPID konfigurieren, damit webpush_configured True ist
    monkeypatch.setattr(settings, "vapid_private_key", "test_private_key")
    monkeypatch.setattr(settings, "vapid_public_key", "test_public_key")

    subscription = {
        "endpoint": "https://push.example.com/xyz",
        "keys": {"auth": "abc", "p256dh": "def"},
    }
    device = PushDevice(
        user_id=user_a.id,
        kind="webpush",
        token=json.dumps(subscription),
        device_name="Browser",
    )
    db.add(device)
    db.commit()
    device_id = device.id

    # Mock: WebPush wirft 410
    from pywebpush import WebPushException

    mock_resp = MagicMock()
    mock_resp.status_code = 410
    error = WebPushException("Gone")
    error.response = mock_resp

    with patch("app.services.notify.webpush", side_effect=error):
        import asyncio
        asyncio.run(notify(user_a.id, "Test", "Body", {}, "test"))

    # Gerät wurde gelöscht
    db.expire_all()
    assert db.query(PushDevice).filter(PushDevice.id == device_id).first() is None


def test_quiet_hours_suppress(db, user_a):
    """Benachrichtigungen werden in Ruhezeiten unterdrückt."""
    from app.services.notify import notify
    from app.models.notification_prefs import NotificationPreference

    # Ruhezeit für user_a: 22:00–08:00
    pref = NotificationPreference(
        user_id=user_a.id,
        category="all",
        enabled=True,
        quiet_start=time(22, 0),
        quiet_end=time(8, 0),
    )
    db.add(pref)

    # Gerät registrieren
    device = PushDevice(
        user_id=user_a.id,
        kind="fcm",
        token="token_quiet",
        device_name="Test Device",
    )
    db.add(device)
    db.commit()

    # Mock: aktuelle Zeit ist 23:00 (in Ruhezeit)
    mock_now = datetime(2026, 10, 14, 23, 0, 0)

    with patch("app.services.notify.NotifyService._send_fcm", new_callable=AsyncMock) as mock_fcm:
        with patch("app.services.notify.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_now
            mock_datetime.strptime = datetime.strptime  # Für time-Parsing

            with patch("app.services.notify.NotifyService.fcm_configured", True):
                import asyncio
                result = asyncio.run(notify(user_a.id, "Test", "Body", {}, "info"))

    # Keine Nachricht wurde gesendet
    assert result == 0
    assert mock_fcm.call_count == 0


def test_category_disabled_suppresses(db, user_a):
    """Deaktivierte Kategorien unterdrücken Benachrichtigungen."""
    from app.services.notify import notify
    from app.models.notification_prefs import NotificationPreference

    # Kategorie "task_assigned" deaktiviert
    pref = NotificationPreference(
        user_id=user_a.id,
        category="task_assigned",
        enabled=False,
    )
    db.add(pref)

    # Gerät registrieren
    device = PushDevice(
        user_id=user_a.id,
        kind="fcm",
        token="token_cat",
        device_name="Test Device",
    )
    db.add(device)
    db.commit()

    with patch("app.services.notify.NotifyService._send_fcm", new_callable=AsyncMock) as mock_fcm:
        with patch("app.services.notify.NotifyService.fcm_configured", True):
            import asyncio
            result = asyncio.run(notify(user_a.id, "Task", "Neue Aufgabe", {}, "task_assigned"))

    # Keine Nachricht gesendet
    assert result == 0
    assert mock_fcm.call_count == 0


def test_push_test_endpoint(client, admin_token):
    """POST /api/push/test sendet Testnachricht."""
    auth = {"Authorization": f"Bearer {admin_token}"}

    # Mock notify-Funktion
    with patch("app.routers.push.notify", new_callable=AsyncMock) as mock_notify:
        mock_notify.return_value = 2  # 2 erfolgreiche Geräte

        resp = client.post("/api/push/test", headers=auth)

    assert resp.status_code == 200
    data = resp.json()
    assert data == 2
    assert mock_notify.called
