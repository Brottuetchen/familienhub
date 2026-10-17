"""Tests für wiederkehrende Erinnerungen."""

from datetime import datetime, timedelta

from app.services.recurrence import advance, next_weekday


def test_advance_units():
    base = datetime(2026, 8, 3, 19, 0)  # Montag
    assert advance(base, "daily") == base + timedelta(days=1)
    assert advance(base, "weekly") == base + timedelta(days=7)
    assert advance(base, "none") is None
    # Freitag -> Montag (Wochenende überspringen)
    friday = datetime(2026, 8, 7, 19, 0)
    assert advance(friday, "weekdays").weekday() == 0
    # monatlich
    assert advance(base, "monthly").month == 9


def test_next_weekday():
    ref = datetime(2026, 8, 3, 10, 0)  # Montag
    d = next_weekday(1, 19, 0, ref=ref)  # nächster Dienstag
    assert d.weekday() == 1 and d.hour == 19 and d.date() == ref.date() + timedelta(days=1)


def test_create_recurring_reminder(client, auth):
    r = client.post("/api/reminders", headers=auth, json={"title": "Rasen mähen", "recurrence": "weekly"})
    assert r.status_code == 200
    assert r.json()["recurrence"] == "weekly"


def test_invalid_recurrence_rejected(client, auth):
    r = client.post("/api/reminders", headers=auth, json={"title": "X", "recurrence": "hourly"})
    assert r.status_code == 400


def test_completing_recurring_rolls_forward(client, auth):
    due = datetime.now().replace(microsecond=0)
    created = client.post(
        "/api/reminders",
        headers=auth,
        json={"title": "Müll", "recurrence": "weekly", "due_at": due.isoformat()},
    ).json()
    rid = created["id"]
    patched = client.patch(f"/api/reminders/{rid}", headers=auth, json={"completed": True}).json()
    # bleibt aktiv, rollt genau eine Woche weiter – gleiche Ortszeit (API liefert UTC mit „Z“)
    from zoneinfo import ZoneInfo

    berlin = ZoneInfo("Europe/Berlin")
    created_local = datetime.fromisoformat(created["due_at"].replace("Z", "+00:00")).astimezone(berlin)
    new_local = datetime.fromisoformat(patched["due_at"].replace("Z", "+00:00")).astimezone(berlin)
    assert patched["completed"] is False
    assert new_local.date() - created_local.date() == timedelta(days=7)
    assert (new_local.hour, new_local.minute) == (created_local.hour, created_local.minute)
