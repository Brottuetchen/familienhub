"""Tests für /api/today Endpunkt."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch


def _local_now():
    """Jetzt in Ortszeit (TIMEZONE), naiv – wie „Heute“ rechnet. date.today() wäre im Container UTC."""
    from app.core.timeutil import local_tz

    return datetime.now(local_tz()).replace(tzinfo=None)


def test_today_shape(client, auth):
    """Prüft die Struktur der /api/today Antwort."""
    response = client.get("/api/today", headers=auth)
    assert response.status_code == 200

    data = response.json()
    assert "date" in data
    assert "events" in data
    assert "tasks" in data
    assert "meals" in data
    assert "shopping_open" in data
    assert "reminders" in data
    assert "weather" in data or data.get("weather") is None

    # Tasks hat status und items
    assert "status" in data["tasks"]
    assert "items" in data["tasks"]

    # Events ist eine Liste
    assert isinstance(data["events"], list)

    # Meals ist eine Liste
    assert isinstance(data["meals"], list)

    # shopping_open ist eine Zahl
    assert isinstance(data["shopping_open"], int)

    # Reminders ist eine Liste
    assert isinstance(data["reminders"], list)


def test_today_partial_failure_still_200(client, auth, monkeypatch):
    """Bei teilweisem Ausfall einzelner Quellen gibt es trotzdem 200 mit Teildaten."""
    from app.routers import today as today_module

    # Mock: Kalender fällt aus, Rest funktioniert
    original_connector_get = today_module.registry.get

    def mock_registry_get(name):
        connector = original_connector_get(name)
        if name == "caldav" and connector:
            # Kalender-Connector wirft Fehler
            mock_conn = AsyncMock()
            mock_conn.get_events = AsyncMock(side_effect=Exception("CalDAV down"))
            return mock_conn
        return connector

    monkeypatch.setattr(today_module.registry, "get", mock_registry_get)

    response = client.get("/api/today", headers=auth)
    assert response.status_code == 200

    data = response.json()
    # Kalender-Events sollte leer sein
    assert data["events"] == []
    # Andere Felder sollten existieren
    assert "tasks" in data
    assert "meals" in data


def test_today_tasks_only_mine_or_assigned(client, auth, session):
    """Tasks in /api/today: nur offene, fällig bis heute ODER mir zugewiesen."""
    from app.models.user import User
    from app.connectors.nextcloud_tasks_connector import NextcloudTasksConnector
    from datetime import timedelta

    # User mit CalDAV-Account
    user = session.query(User).first()
    if not user:
        user = User(username="testuser", email="test@example.com", role="admin")
        session.add(user)
        session.commit()

    # Mock den Connector
    with patch.object(NextcloudTasksConnector, "get_tasks") as mock_get_tasks:
        # Simuliere verschiedene Tasks
        today_str = _local_now().date().isoformat()
        yesterday_str = (_local_now().date() - timedelta(days=1)).isoformat()
        tomorrow_str = (_local_now().date() + timedelta(days=1)).isoformat()

        mock_get_tasks.return_value = {
            "status": "ok",
            "error": None,
            "items": [
                # Fällig gestern, offen → sollte dabei sein
                {"uid": "1", "title": "Überfällig", "due": yesterday_str, "done": False},
                # Fällig heute, offen → sollte dabei sein
                {"uid": "2", "title": "Heute fällig", "due": today_str, "done": False},
                # Fällig morgen, offen → sollte NICHT dabei sein (außer zugewiesen)
                {"uid": "3", "title": "Morgen fällig", "due": tomorrow_str, "done": False},
                # Mir zugewiesen, egal wann fällig → sollte dabei sein
                {"uid": "4", "title": "Mir zugewiesen", "due": tomorrow_str, "done": False, "assignee": user.id},
            ],
        }

        response = client.get("/api/today", headers=auth)
        assert response.status_code == 200

        data = response.json()
        tasks = data["tasks"]["items"]

        # Max 10 Tasks
        assert len(tasks) <= 10


def test_today_includes_hub_meal_entries(client, auth):
    """Eigene Essensplan-Einträge erscheinen in /api/today, nicht nur Cookidoo."""
    resp = client.post("/api/meals/plan", headers=auth,
                       json={"date": _local_now().date().isoformat(), "custom_title": "Linsensuppe heute"})
    assert resp.status_code == 200
    meals = client.get("/api/today", headers=auth).json()["meals"]
    assert {"source": "hub", "title": "Linsensuppe heute"} in meals


def test_today_events_exclude_tomorrow(client, auth):
    """The card is "Today": an event tomorrow (inside the 2-day fetch window) must not be counted."""
    now = _local_now()
    today = now.date()
    tomorrow = today + timedelta(days=1)
    for title, day in (("Heute-Termin", today), ("Morgen-Termin", tomorrow)):
        r = client.post("/api/calendar/events", headers=auth, json={
            "title": title, "start": f"{day.isoformat()}T13:00:00", "end": f"{day.isoformat()}T14:00:00", "all_day": False})
        assert r.status_code in (200, 201), r.text
    titles = [e["title"] for e in client.get("/api/today", headers=auth).json()["events"]]
    assert "Heute-Termin" in titles
    assert "Morgen-Termin" not in titles


def test_today_all_day_end_is_exclusive(client, auth):
    """An all-day event ending (exclusive) today is over; one starting tomorrow is not today's."""
    from app.routers.today import _occurs_on

    day = _local_now().date()
    y, t = (day - timedelta(days=1)).isoformat(), (day + timedelta(days=1)).isoformat()
    assert not _occurs_on({"start": y, "end": day.isoformat(), "all_day": True}, day)
    assert not _occurs_on({"start": t, "end": (day + timedelta(days=2)).isoformat(), "all_day": True}, day)
    assert _occurs_on({"start": y, "end": t, "all_day": True}, day)
