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


CALS = [{"id": "caldav:privat", "name": "Persönlich", "color": None, "url": "https://dav.example.test/c/anna/personal/"},
        {"id": "caldav:fam", "name": "Familie", "color": "#81B29A", "url": "https://dav.example.test/c/anna/familie_shared/"}]


def test_family_calendar_is_marked_and_first(client, monkeypatch):
    from app.connectors import caldav_connector
    from app.services import config_store

    monkeypatch.setitem(config_store._extra, "CALDAV_FAMILY_CALENDAR", "familie")
    monkeypatch.setattr(caldav_connector.CalDAVConnector, "_list_calendars_sync", lambda self: CALS)
    cals = client.get("/api/calendar/calendars", headers=_auth(client, "cl_fam", caldav=True)).json()
    assert [c["id"] for c in cals if c["family"]][:2] == ["hub", "caldav:fam"]
    assert cals.index(next(c for c in cals if c["id"] == "caldav:fam")) < cals.index(next(c for c in cals if c["id"] == "caldav:privat"))


def test_create_goes_exactly_into_the_chosen_caldav_calendar(client, monkeypatch):
    from app.connectors import caldav_connector

    seen = {}

    def fake_create(self, title, start, end, all_day, calendar_url=None, **extras):
        seen.update(url=calendar_url, **extras)
        return {"uid": "u1", "title": title, "start": start, "end": end, "all_day": all_day}

    monkeypatch.setattr(caldav_connector.CalDAVConnector, "_list_calendars_sync", lambda self: CALS)
    monkeypatch.setattr(caldav_connector.CalDAVConnector, "_create_event_sync", fake_create)
    h = _auth(client, "cl_target", caldav=True)
    r = client.post("/api/calendar/events", headers=h, json={
        "title": "Elternabend", "start": "2099-03-03T19:00:00", "end": "2099-03-03T21:00:00", "all_day": False,
        "calendar_id": "caldav:fam", "location": "Aula", "notes": "Mappe mitbringen", "recurrence": "monthly"})
    assert r.status_code == 201, r.text
    assert seen == {"url": "https://dav.example.test/c/anna/familie_shared/", "location": "Aula",
                    "notes": "Mappe mitbringen", "rrule": "MONTHLY"}
    bad = client.post("/api/calendar/events", headers=h, json={
        "title": "x", "start": "2099-03-03T19:00:00", "end": "2099-03-03T20:00:00", "all_day": False, "calendar_id": "caldav:gibtsnicht"})
    assert bad.status_code == 422
    ics = client.post("/api/calendar/events", headers=h, json={
        "title": "x", "start": "2099-03-03T19:00:00", "end": "2099-03-03T20:00:00", "all_day": False, "calendar_id": "ics:schulferien"})
    assert ics.status_code == 422


def test_hub_event_with_details_and_weekly_repeat(client):
    h = _auth(client, "cl_repeat")
    r = client.post("/api/calendar/events", headers=h, json={
        "title": "Schwimmkurs", "start": "2099-04-06T16:00:00", "end": "2099-04-06T17:00:00", "all_day": False,
        "calendar_id": "hub", "location": "Hallenbad", "notes": "Badekappe", "recurrence": "weekly"})
    assert r.status_code == 201 and r.json()["location"] == "Hallenbad" and r.json()["recurrence"] == "weekly"
    april = client.get("/api/calendar/events", params={"start": "2099-04-01", "days": 30}, headers=h).json()
    starts = sorted(e["start"] for e in april if e["title"] == "Schwimmkurs")
    assert starts == ["2099-04-06T16:00:00", "2099-04-13T16:00:00", "2099-04-20T16:00:00", "2099-04-27T16:00:00"]
    later = client.get("/api/calendar/events", params={"start": "2099-12-01", "days": 7}, headers=h).json()
    assert any(e["title"] == "Schwimmkurs" for e in later)  # still repeats months later
    assert client.post("/api/calendar/events", headers=h, json={
        "title": "x", "start": "2099-04-06T16:00:00", "end": "2099-04-06T17:00:00", "all_day": False,
        "recurrence": "hourly"}).status_code == 422


def test_edit_hub_event(client):
    h = _auth(client, "cl_edit")
    ev = client.post("/api/calendar/events", headers=h, json={
        "title": "Probe", "start": "2099-09-01T10:00:00", "end": "2099-09-01T11:00:00", "all_day": False, "calendar_id": "hub"}).json()
    r = client.put(f"/api/calendar/events/{ev['id']}", headers=h, json={
        "title": "Generalprobe", "start": "2099-09-02T18:00:00", "end": "2099-09-02T20:00:00", "all_day": False,
        "location": "Bühne", "notes": "Kostüm", "recurrence": "none"})
    assert r.status_code == 200 and r.json()["title"] == "Generalprobe" and r.json()["location"] == "Bühne"
    sept = client.get("/api/calendar/events", params={"start": "2099-09-01", "days": 3}, headers=h).json()
    e = next(x for x in sept if x["id"] == ev["id"])
    assert e["start"] == "2099-09-02T18:00:00" and e["notes"] == "Kostüm"
    assert client.put("/api/calendar/events/999999", headers=h, json={
        "title": "x", "start": "2099-09-02T18:00:00", "end": "2099-09-02T19:00:00", "all_day": False}).status_code == 404
    kid = _auth(client, "cl_edit_kid", role="child")
    assert client.put(f"/api/calendar/events/{ev['id']}", headers=kid, json={
        "title": "x", "start": "2099-09-02T18:00:00", "end": "2099-09-02T19:00:00", "all_day": False}).status_code == 403


def test_edit_and_delete_own_caldav_event(client, monkeypatch):
    from app.connectors import caldav_connector

    calls = []
    monkeypatch.setattr(caldav_connector.CalDAVConnector, "_list_calendars_sync", lambda self: CALS)
    monkeypatch.setattr(caldav_connector.CalDAVConnector, "_update_event_sync",
                        lambda self, url, uid, changes: calls.append(("update", url, uid, changes["title"])) or uid == "u1")
    monkeypatch.setattr(caldav_connector.CalDAVConnector, "_delete_event_sync",
                        lambda self, url, uid: calls.append(("delete", url, uid)) or uid == "u1")
    h = _auth(client, "cl_caldav_edit", caldav=True)
    body = {"title": "Neu", "start": "2099-03-03T19:00:00", "end": "2099-03-03T20:00:00", "all_day": False}
    assert client.put("/api/calendar/caldav/caldav:fam/u1", headers=h, json=body).status_code == 200
    assert client.put("/api/calendar/caldav/caldav:fam/nope", headers=h, json=body).status_code == 404
    assert client.put("/api/calendar/caldav/caldav:fremd/u1", headers=h, json=body).status_code == 404  # not her calendar
    assert client.delete("/api/calendar/caldav/caldav:fam/u1", headers=h).status_code == 204
    assert calls[0] == ("update", "https://dav.example.test/c/anna/familie_shared/", "u1", "Neu")
    assert calls[-1] == ("delete", "https://dav.example.test/c/anna/familie_shared/", "u1")
    assert ("update", "https://dav.example.test/c/anna/familie_shared/", "u1", "Neu") in calls
