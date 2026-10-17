"""Tests für POST /api/calendar/events."""

from unittest.mock import patch


def test_create_event_uses_user_account(client, auth, session):
    """POST /api/calendar/events nutzt das CalDAV-Konto des Nutzers."""
    from app.models.user import User
    from app.models.caldav import CalDAVAccount
    from app.core.crypto import encrypt

    user = session.query(User).filter(User.username == "admin").first()
    if not user:
        user = User(username="testuser", email="test@example.com", role="admin")
        session.add(user)
        session.commit()

    # CalDAV-Account für den User
    account = CalDAVAccount(
        user_id=user.id,
        url="https://cloud.example.com/remote.php/dav",
        username="testuser",
        password_enc=encrypt("secret123"),
    )
    session.add(account)
    session.commit()

    # Mock CalDAVConnector.create_event
    async def mock_create_event(*args, **kwargs):
        return {
            "uid": "test-uid-123",
            "title": "Zahnarzt",
            "start": "2024-12-20T10:00:00",
            "end": "2024-12-20T11:00:00",
            "all_day": False,
        }

    with patch("app.connectors.caldav_connector.CalDAVConnector.create_event", new=mock_create_event):
        response = client.post(
            "/api/calendar/events",
            headers=auth,
            json={
                "title": "Zahnarzt",
                "start": "2024-12-20T10:00:00",
                "end": "2024-12-20T11:00:00",
                "all_day": False,
            },
        )

        # Sollte erfolgreich sein
        if response.status_code != 201:
            print(f"Error response: {response.json()}")
        assert response.status_code == 201


def test_create_event_without_account_409(client, auth, session):
    """POST /api/calendar/events ohne CalDAV-Konto → 409."""
    from app.models.user import User
    from app.models.caldav import CalDAVAccount

    user = session.query(User).filter(User.username == "admin").first()
    if not user:
        user = User(username="testuser", email="test@example.com", role="admin")
        session.add(user)
        session.commit()

    # Sicherstellen, dass kein CalDAV-Account existiert
    session.query(CalDAVAccount).filter(CalDAVAccount.user_id == user.id).delete()
    session.commit()

    response = client.post(
        "/api/calendar/events",
        headers=auth,
        json={
            "title": "Zahnarzt",
            "start": "2024-12-20T10:00:00",
            "end": "2024-12-20T11:00:00",
            "all_day": False,
        },
    )

    assert response.status_code == 409
    data = response.json()
    detail = data.get("detail", {})
    assert detail.get("error") == "no_caldav_account"
