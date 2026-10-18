"""Calendar list for colours, filters and choosing the target of a new event."""

from app.core.crypto import encrypt
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.caldav import CalDAVAccount
from app.models.user import User


def _auth(client, name, role="partner", caldav=False):
    with SessionLocal() as db:
        u = db.query(User).filter(User.username == name).first()
        if not u:
            u = User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"), role=role)
            db.add(u)
            db.commit()
            db.refresh(u)
        if caldav and not db.query(CalDAVAccount).filter(CalDAVAccount.user_id == u.id).first():
            db.add(CalDAVAccount(user_id=u.id, url="https://dav.example.test/remote.php/dav", username=name,
                                 password_enc=encrypt("pw")))
            db.commit()
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_calendar_ids_are_stable_and_hide_the_url():
    from app.connectors.caldav_connector import calendar_id

    a = calendar_id("https://dav.example.test/calendars/anna/familie/")
    assert a == calendar_id("https://dav.example.test/calendars/anna/familie")
    assert a.startswith("caldav:") and "anna" not in a


def test_list_contains_hub_own_caldav_and_subscriptions(client, monkeypatch):
    from app.connectors import caldav_connector
    from app.services import config_store

    monkeypatch.setitem(config_store._extra, "ICS_FEEDS", "Schulferien | https://feeds.example.test/f.ics")
    monkeypatch.setattr(caldav_connector.CalDAVConnector, "_list_calendars_sync", lambda self: [
        {"id": "caldav:abc", "name": "Persönlich", "color": "#3D85C6", "url": "https://dav.example.test/c/p/"},
        {"id": "caldav:def", "name": "Familie (Nextcloud)", "color": None, "url": "https://dav.example.test/c/f/"}])
    cals = client.get("/api/calendar/calendars", headers=_auth(client, "cl_anna", caldav=True)).json()
    by_id = {c["id"]: c for c in cals}
    assert by_id["hub"]["writable"] is True and by_id["hub"]["family"] is True
    assert by_id["caldav:abc"] == {"id": "caldav:abc", "name": "Persönlich", "source": "caldav", "color": "#3D85C6",
                                   "writable": True, "family": False}
    assert by_id["ics:schulferien"]["writable"] is False
    assert "url" not in by_id["caldav:def"]


def test_children_cannot_write_and_see_no_foreign_caldav(client):
    cals = client.get("/api/calendar/calendars", headers=_auth(client, "cl_kid", role="child")).json()
    assert [c["id"] for c in cals if c["source"] == "caldav"] == []
    assert next(c for c in cals if c["id"] == "hub")["writable"] is False


def test_hub_events_carry_the_calendar_id(client):
    h = _auth(client, "cl_ev")
    client.post("/api/calendar/events", headers=h, json={
        "title": "Mit Kennung", "start": "2099-08-01T10:00:00", "end": "2099-08-01T11:00:00", "all_day": False})
    events = client.get("/api/calendar/events", params={"start": "2099-08-01", "days": 1}, headers=h).json()
    assert next(e for e in events if e["title"] == "Mit Kennung")["calendar_id"] == "hub"
