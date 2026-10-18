"""Sources per area (step 2): the admin chooses where tasks, shopping and events come from."""

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User


def _auth(client, name, role="partner"):
    with SessionLocal() as db:
        if not db.query(User).filter(User.username == name).first():
            db.add(User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"),
                        role=role, is_admin=role == "admin"))
            db.commit()
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _area(body, name):
    return next(a for a in body["areas"] if a["area"] == name)


def test_sources_overview_lists_areas_and_choices(client, auth):
    body = client.get("/api/admin/sources", headers=auth).json()
    tasks, shopping, calendar = _area(body, "tasks"), _area(body, "shopping"), _area(body, "calendar")
    assert tasks["multiple"] is True and shopping["multiple"] is False and calendar["multiple"] is True
    ids = {s["id"] for s in tasks["sources"]}
    assert {"hub_tasks", "nextcloud", "habitica"} <= ids
    hub = next(s for s in shopping["sources"] if s["id"] == "hub_shopping")
    assert hub["selected"] is True and hub["fallback"] is True  # no Home Assistant in tests
    assert next(s for s in calendar["sources"] if s["id"] == "hub_calendar")["selected"] is True


def test_only_admins(client):
    h = _auth(client, "src_partner")
    assert client.get("/api/admin/sources", headers=h).status_code == 403
    assert client.put("/api/admin/sources", headers=h, json={"area": "tasks", "selected": ["hub_tasks"]}).status_code == 403


def test_choose_task_sources(client, auth):
    try:
        r = client.put("/api/admin/sources", headers=auth, json={"area": "tasks", "selected": ["hub_tasks"]})
        assert r.status_code == 200, r.text
        assert {p["id"] for p in client.get("/api/tasks/providers", headers=auth).json()["items"]} == {"hub_tasks"}
        body = client.get("/api/admin/sources", headers=auth).json()
        sel = {s["id"] for s in _area(body, "tasks")["sources"] if s["selected"]}
        assert sel == {"hub_tasks"}
        # a source that is not selected cannot be used directly either
        assert client.get("/api/tasks", params={"provider": "nextcloud"}, headers=auth).status_code == 409
    finally:
        client.put("/api/admin/sources", headers=auth, json={"area": "tasks", "selected": []})  # back to "all active"


def test_choose_shopping_source_and_validation(client, auth):
    try:
        assert client.put("/api/admin/sources", headers=auth,
                          json={"area": "shopping", "selected": ["nextcloud"]}).status_code == 422  # cannot shop
        assert client.put("/api/admin/sources", headers=auth,
                          json={"area": "shopping", "selected": ["hub_shopping", "homeassistant"]}).status_code == 422  # one only
        assert client.put("/api/admin/sources", headers=auth, json={"area": "nope", "selected": []}).status_code == 422
        assert client.put("/api/admin/sources", headers=auth,
                          json={"area": "shopping", "selected": ["hub_shopping"]}).status_code == 200
        from app.plugins.base import get_setting
        assert get_setting("SHOPPING_SOURCE") == "hub_shopping"
    finally:
        client.put("/api/admin/sources", headers=auth, json={"area": "shopping", "selected": []})


def test_calendar_sources_exclude_hub(client, auth):
    try:
        assert client.put("/api/admin/sources", headers=auth, json={"area": "calendar", "selected": ["nextcloud"]}).status_code == 200
        r = client.post("/api/calendar/events", headers=auth, json={
            "title": "Ohne Hub", "start": "2099-03-03T10:00:00", "end": "2099-03-03T11:00:00", "all_day": False})
        assert r.status_code == 409  # neither CalDAV account nor hub calendar
    finally:
        client.put("/api/admin/sources", headers=auth, json={"area": "calendar", "selected": []})
