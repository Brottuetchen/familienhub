"""Move a calendar event, and keep a template as its own assignable list."""

from unittest.mock import patch

import pytest

from app.core.security import get_password_hash
from app.models.hub import HubEvent, HubShoppingItem
from app.models.user import User


def _person(session, username):
    row = session.query(User).filter(User.username == username).first()
    if row:
        return row
    row = User(username=username, email=f"{username}@test.de", hashed_password=get_password_hash("x"),
               full_name=username, role="partner", is_active=True)
    session.add(row)
    session.commit()
    return row


def test_template_becomes_separate_assignable_list(client, auth, session):
    sam = _person(session, "sam")
    created = client.post("/api/templates", headers=auth, json={
        "name": "Packen",
        "items": [{"name": "Zahnbürste", "note": ""}, {"name": "Ladegerät", "note": ""}],
    })
    assert created.status_code == 201, created.text
    template_id = created.json()["id"]
    item_ids = [i["id"] for i in created.json()["items"]]

    applied = client.post(f"/api/templates/{template_id}/apply/list", headers=auth, json={
        "name": "Packliste Urlaub", "kind": "shopping", "assignee_id": sam.id, "item_ids": item_ids[:1],
    })
    assert applied.status_code == 201, applied.text
    body = applied.json()
    assert body["name"] == "Packliste Urlaub"
    assert body["assignee_id"] == sam.id
    assert [i["summary"] for i in body["items"]] == ["Zahnbürste"]
    assert body["items"][0]["assignee_id"] == sam.id

    shopping = client.get("/api/shopping", headers=auth)
    assert shopping.status_code == 200, shopping.text
    summaries = [i["summary"] for g in shopping.json().get("groups", []) for i in g["items"]]
    assert "Zahnbürste" not in summaries

    listed = client.get("/api/lists?kind=shopping", headers=auth).json()["items"]
    assert any(i["name"] == "Packliste Urlaub" for i in listed)

    only_sam = client.get(f"/api/lists?kind=shopping&assignee_id={sam.id}", headers=auth).json()["items"]
    assert [i["name"] for i in only_sam] == ["Packliste Urlaub"]

    list_id = body["id"]
    item_id = body["items"][0]["id"]
    own = client.patch(f"/api/lists/{list_id}/items/{item_id}", headers=auth, json={"assignee_id": None})
    assert own.status_code == 200, own.text
    # cleared item follows the list again
    assert own.json()["assignee_id"] == sam.id
    assert own.json()["own_assignee"] is False

    admin = session.query(User).filter(User.username == "admin").one()
    moved = client.patch(f"/api/lists/{list_id}", headers=auth, json={"assignee_id": admin.id})
    assert moved.status_code == 200, moved.text
    assert moved.json()["items"][0]["assignee_id"] == admin.id

    kept = client.patch(f"/api/lists/{list_id}/items/{item_id}", headers=auth, json={"assignee_id": sam.id})
    assert kept.status_code == 200
    again = client.patch(f"/api/lists/{list_id}", headers=auth, json={"assignee_id": admin.id})
    assert again.json()["items"][0]["assignee_id"] == sam.id  # individual assignment stays


def _caldav_account(session):
    from app.core.crypto import encrypt
    from app.models.caldav import CalDAVAccount

    user = session.query(User).filter(User.username == "admin").one()
    row = session.query(CalDAVAccount).filter(CalDAVAccount.user_id == user.id).first()
    if row:
        return row
    row = CalDAVAccount(user_id=user.id, url="https://cloud.example/remote.php/dav",
                        username="admin", password_enc=encrypt("x"))
    session.add(row)
    session.commit()
    return row


@pytest.fixture
def caldav_account(session):
    from app.models.caldav import CalDAVAccount

    row = _caldav_account(session)
    yield row
    session.query(CalDAVAccount).filter(CalDAVAccount.user_id == row.user_id).delete()
    session.commit()


def test_move_hub_event_into_caldav_calendar(client, auth, session, caldav_account):
    created = client.post("/api/calendar/events", headers=auth, json={
        "title": "Zahnarzt", "start": "2024-12-20T10:00:00", "end": "2024-12-20T11:00:00",
        "all_day": False, "calendar_id": "hub",
    })
    assert created.status_code == 201, created.text
    event_id = created.json()["id"]

    async def calendars(*_a, **_k):
        return [{"id": "caldav:abc", "name": "Privat", "url": "https://cloud.example/cal", "color": None}]

    async def create_event(*_a, **kwargs):
        return {"uid": "moved-1", "title": kwargs["title"], "start": kwargs["start"], "end": kwargs["end"],
                "all_day": kwargs["all_day"]}

    with patch("app.connectors.caldav_connector.CalDAVConnector.list_calendars", new=calendars), \
            patch("app.connectors.caldav_connector.CalDAVConnector.create_event", new=create_event), \
            patch("app.routers.calendar._caldav_active", return_value=True):
        moved = client.post("/api/calendar/move", headers=auth, json={
            "from_calendar_id": "hub", "to_calendar_id": "caldav:abc", "event_id": event_id,
        })
    assert moved.status_code == 200, moved.text
    assert moved.json()["event"]["uid"] == "moved-1"
    assert session.get(HubEvent, event_id) is None


def test_move_rolls_back_when_source_delete_fails(client, auth, session, caldav_account):
    async def calendars(*_a, **_k):
        return [{"id": "caldav:abc", "name": "Privat", "url": "https://cloud.example/cal", "color": None}]

    async def read_event(*_a, **_k):
        return {"title": "Bleibt", "start": "2024-12-20T10:00:00", "end": "2024-12-20T11:00:00",
                "all_day": False, "recurrence": "weekly", "location": None, "notes": None, "alarm_minutes": 15}

    async def delete_event(*_a, **_k):
        return False

    with patch("app.connectors.caldav_connector.CalDAVConnector.list_calendars", new=calendars), \
            patch("app.connectors.caldav_connector.CalDAVConnector.read_event", new=read_event), \
            patch("app.connectors.caldav_connector.CalDAVConnector.delete_event", new=delete_event), \
            patch("app.routers.calendar._caldav_active", return_value=True):
        moved = client.post("/api/calendar/move", headers=auth, json={
            "from_calendar_id": "caldav:abc", "to_calendar_id": "hub", "uid": "src-1",
        })
    assert moved.status_code == 502, moved.text
    assert session.query(HubEvent).filter(HubEvent.title == "Bleibt").count() == 0


def test_named_shopping_item_stays_off_the_main_list(client, auth, session):
    created = client.post("/api/lists", headers=auth, json={"kind": "shopping", "name": "Packliste"})
    assert created.status_code == 201, created.text
    added = client.post(f"/api/lists/{created.json()['id']}/items", headers=auth, json={"summary": "Sonnencreme"})
    assert added.status_code == 201, added.text
    assert session.query(HubShoppingItem).filter(HubShoppingItem.summary == "Sonnencreme").count() == 1
    shopping = client.get("/api/shopping", headers=auth)
    summaries = [i["summary"] for g in shopping.json().get("groups", []) for i in g["items"]]
    assert "Sonnencreme" not in summaries
    overview = client.get("/api/lists?kind=shopping&with_items=true", headers=auth)
    assert overview.status_code == 200, overview.text
    row = next(i for i in overview.json()["items"] if i["name"] == "Packliste")
    assert [i["summary"] for i in row["items"]] == ["Sonnencreme"]
