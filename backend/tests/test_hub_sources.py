"""Built-in sources: tasks, shopping list and calendar work without any external service."""

import pytest

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User


def _user(name, role="partner"):
    with SessionLocal() as db:
        u = db.query(User).filter(User.username == name).first()
        if not u:
            u = User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"), role=role,
                     is_admin=role == "admin")
            db.add(u)
            db.commit()
            db.refresh(u)
        return u.id


def _auth(client, name, role="partner"):
    _user(name, role)
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _account(client, h):
    hub = [p for p in client.get("/api/tasks/providers", headers=h).json()["items"] if p["id"] == "hub_tasks"]
    assert hub and hub[0]["configured"] is True, hub
    return hub[0]["account"]


def _create(client, h, account, **body):
    r = client.post("/api/tasks", params={"provider": "hub_tasks", "account": account}, headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _view(client, h, view, account=None):
    params = {"provider": "hub_tasks", "view": view}
    if account:
        params["account"] = account
    r = client.get("/api/tasks", params=params, headers=h)
    assert r.status_code == 200, r.text
    return {t["title"] for t in r.json()["items"]}


# --- tasks ---

def test_hub_tasks_views_follow_assignment(client):
    anna, ben = _auth(client, "hub_anna"), _auth(client, "hub_ben")
    ben_id = _user("hub_ben")
    acc_a, acc_b = _account(client, anna), _account(client, ben)
    _create(client, anna, acc_a, title="Anna privat")
    _create(client, anna, acc_a, title="Für Ben", assignee_id=ben_id)
    _create(client, anna, acc_a, title="Für alle", list="family")

    assert _view(client, anna, "mine", acc_a) == {"Anna privat"}
    assert _view(client, anna, "from_me", acc_a) == {"Für Ben"}
    assert {"Für alle"} <= _view(client, anna, "family", acc_a)
    assert _view(client, ben, "for_me", acc_b) == {"Für Ben"}
    assert "Für Ben" in _view(client, ben, "mine", acc_b)  # overview includes assigned tasks
    # family tasks: assigned to someone count for that person; self-assigned ones are not "from me"
    _create(client, anna, acc_a, title="Familie für Ben", list="family", assignee_id=ben_id)
    _create(client, anna, acc_a, title="Familie für Anna", list="family", assignee_id=_user("hub_anna"))
    assert {"Familie für Ben"} <= _view(client, ben, "mine", acc_b) and "Familie für Ben" in _view(client, ben, "for_me", acc_b)
    assert "Familie für Anna" in _view(client, anna, "mine", acc_a)
    assert "Familie für Anna" not in _view(client, anna, "from_me", acc_a)
    assert "Familie für Ben" in _view(client, anna, "from_me", acc_a)
    assert "Für alle" not in _view(client, anna, "mine", acc_a)
    # private tasks stay private
    assert "Anna privat" not in _view(client, ben, "all", acc_b)
    created = client.get("/api/tasks", params={"provider": "hub_tasks", "view": "for_me", "account": acc_b}, headers=ben).json()["items"][0]
    assert created["provider"] == "hub_tasks" and created["list"]["kind"] == "personal"
    assert created["created_by"] == _user("hub_anna") and created["assignee"] == ben_id


def test_hub_tasks_complete_update_delete(client):
    h = _auth(client, "hub_carl")
    acc = _account(client, h)
    t = _create(client, h, acc, title="Wäsche", due="2026-10-20", notes="60 Grad")
    uid = t["uid"]
    assert t["due"] == "2026-10-20" and t["notes"] == "60 Grad" and t["done"] is False

    r = client.patch(f"/api/tasks/{uid}", params={"provider": "hub_tasks", "account": acc}, headers=h, json={"title": "Wäsche aufhängen"})
    assert r.status_code == 200 and r.json()["title"] == "Wäsche aufhängen"
    r = client.post(f"/api/tasks/{uid}/complete", params={"provider": "hub_tasks", "account": acc}, headers=h)
    assert r.status_code == 200 and r.json()["done"] is True
    assert "Wäsche aufhängen" not in _view(client, h, "mine", acc)
    r = client.get("/api/tasks", params={"provider": "hub_tasks", "view": "mine", "account": acc, "include_done": True}, headers=h)
    assert "Wäsche aufhängen" in {x["title"] for x in r.json()["items"]}
    assert client.delete(f"/api/tasks/{uid}", params={"provider": "hub_tasks", "account": acc}, headers=h).status_code == 204
    assert client.delete(f"/api/tasks/{uid}", params={"provider": "hub_tasks", "account": acc}, headers=h).status_code == 404


def test_hub_tasks_of_others_cannot_be_touched(client):
    a, b = _auth(client, "hub_dora"), _auth(client, "hub_emil")
    t = _create(client, a, _account(client, a), title="Doras Geheimnis")
    acc_b = _account(client, b)
    for method, path in (("patch", f"/api/tasks/{t['uid']}"), ("post", f"/api/tasks/{t['uid']}/complete"),
                         ("delete", f"/api/tasks/{t['uid']}")):
        kw = {"json": {"title": "x"}} if method == "patch" else {}
        r = getattr(client, method)(path, params={"provider": "hub_tasks", "account": acc_b}, headers=b, **kw)
        assert r.status_code == 404, (method, r.status_code)


def test_hub_household_rotation_moves_to_next_person(client):
    a = _auth(client, "hub_rot_a")
    ids = [_user("hub_rot_a"), _user("hub_rot_b"), _user("hub_rot_c")]
    acc = _account(client, a)
    t = _create(client, a, acc, title="Bad putzen", list="family", due="2026-10-19", recurrence="weekly", rotation=ids)
    assert t["assignee"] == ids[0] and t["rotation"] == ids
    done = client.post(f"/api/tasks/{t['uid']}/complete", params={"provider": "hub_tasks", "account": acc}, headers=a)
    assert done.status_code == 200
    family = client.get("/api/tasks", params={"provider": "hub_tasks", "view": "family", "account": acc}, headers=a).json()["items"]
    nxt = [x for x in family if x["title"] == "Bad putzen" and not x["done"]]
    assert len(nxt) == 1 and nxt[0]["assignee"] == ids[1] and nxt[0]["due"] == "2026-10-26"
    # completing twice does not create a second successor
    client.post(f"/api/tasks/{t['uid']}/complete", params={"provider": "hub_tasks", "account": acc}, headers=a)
    family = client.get("/api/tasks", params={"provider": "hub_tasks", "view": "family", "account": acc}, headers=a).json()["items"]
    assert len([x for x in family if x["title"] == "Bad putzen" and not x["done"]]) == 1


def test_child_completes_only_own_household_turn(client):
    a = _auth(client, "hub_parent")
    kid = _auth(client, "hub_kid", role="child")
    ids = [_user("hub_parent"), _user("hub_kid")]
    acc = _account(client, a)
    t = _create(client, a, acc, title="Spülmaschine", list="family", due="2026-10-19", recurrence="daily", rotation=ids)
    r = client.post(f"/api/tasks/{t['uid']}/complete", params={"provider": "hub_tasks", "account": _account(client, kid)}, headers=kid)
    assert r.status_code == 403


def test_hub_tasks_in_today_and_all_providers(client):
    h = _auth(client, "hub_today")
    acc = _account(client, h)
    _create(client, h, acc, title="Heute fällig", due="2000-01-01")
    titles = {t["title"] for t in client.get("/api/today", headers=h).json()["tasks"]["items"]}
    assert "Heute fällig" in titles
    merged = client.get("/api/tasks", params={"provider": "all", "view": "mine"}, headers=h).json()
    assert "Heute fällig" in {t["title"] for t in merged["items"]}


# --- shopping ---

@pytest.fixture
def hub_shopping(monkeypatch):
    """Without Home Assistant, the shopping list comes from the hub."""
    from app.config import settings

    monkeypatch.setattr(settings, "homeassistant_url", None)
    monkeypatch.setattr(settings, "homeassistant_token", None)


def test_hub_shopping_add_tick_delete_recent(client, hub_shopping):
    h = _auth(client, "hub_shop")
    r = client.get("/api/shopping", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "ok", r.text
    assert client.post("/api/shopping", headers=h, json={"item": "Hafermilch"}).status_code == 200
    groups = client.get("/api/shopping", headers=h).json()["groups"]
    manual = next(g for g in groups if g["key"] == "manual")["items"]
    item = next(i for i in manual if i["summary"] == "Hafermilch")
    assert item["status"] == "needs_action"
    assert client.get("/api/today", headers=h).json()["shopping_open"] >= 1

    assert client.patch(f"/api/shopping/{item['uid']}", headers=h, json={"done": True}).status_code == 200
    manual = next(g for g in client.get("/api/shopping", headers=h).json()["groups"] if g["key"] == "manual")["items"]
    assert next(i for i in manual if i["uid"] == item["uid"])["status"] == "completed"
    assert "Hafermilch" in client.get("/api/shopping/recent", headers=h).json()
    assert client.delete(f"/api/shopping/{item['uid']}", headers=h).status_code == 200
    assert client.patch(f"/api/shopping/{item['uid']}", headers=h, json={"done": False}).status_code == 404


def test_hub_shopping_is_shared_by_the_family(client, hub_shopping):
    a, b = _auth(client, "hub_shop_a"), _auth(client, "hub_shop_b")
    client.post("/api/shopping", headers=a, json={"item": "Brezeln"})
    manual = next(g for g in client.get("/api/shopping", headers=b).json()["groups"] if g["key"] == "manual")["items"]
    assert "Brezeln" in {i["summary"] for i in manual}


def test_shopping_source_can_be_chosen(client, monkeypatch):
    """With Home Assistant configured, the admin can still choose the hub list."""
    from app.config import settings
    from app.services import config_store

    monkeypatch.setattr(settings, "homeassistant_url", "http://ha.test:8123")
    monkeypatch.setattr(settings, "homeassistant_token", "t")
    monkeypatch.setitem(config_store._extra, "SHOPPING_SOURCE", "hub_shopping")
    h = _auth(client, "hub_shop_src")
    client.post("/api/shopping", headers=h, json={"item": "Senf"})
    manual = next(g for g in client.get("/api/shopping", headers=h).json()["groups"] if g["key"] == "manual")["items"]
    assert "Senf" in {i["summary"] for i in manual}


# --- calendar ---

def test_hub_calendar_without_caldav_account(client):
    a, b = _auth(client, "hub_cal_a"), _auth(client, "hub_cal_b")
    r = client.post("/api/calendar/events", headers=a, json={
        "title": "Kinderarzt", "start": "2099-05-04T10:00:00", "end": "2099-05-04T11:00:00", "all_day": False})
    assert r.status_code == 201, r.text
    assert r.json()["source"] == "hub"
    # family calendar: everyone sees it
    events = client.get("/api/calendar/events", params={"start": "2099-05-01", "days": 31}, headers=b).json()
    assert any(e["title"] == "Kinderarzt" and e["source"] == "hub" for e in events)


def test_hub_calendar_in_today(client):
    from datetime import datetime

    from app.core.timeutil import local_tz

    h = _auth(client, "hub_cal_today")
    # "today" in the hub's time zone; the build server runs in UTC (failed between 00:00 and 02:00 CEST)
    now = datetime.now(local_tz()).replace(microsecond=0, tzinfo=None)
    client.post("/api/calendar/events", headers=h, json={
        "title": "Heute Abend", "start": now.replace(hour=23, minute=0).isoformat(),
        "end": now.replace(hour=23, minute=30).isoformat(), "all_day": False})
    assert "Heute Abend" in {e["title"] for e in client.get("/api/today", headers=h).json()["events"]}


def test_hub_calendar_all_day_and_validation(client):
    h = _auth(client, "hub_cal_val")
    r = client.post("/api/calendar/events", headers=h, json={
        "title": "Ferien", "start": "2099-07-01", "end": "2099-07-02", "all_day": True})
    assert r.status_code == 201 and r.json()["all_day"] is True
    bad = client.post("/api/calendar/events", headers=h, json={
        "title": "Rückwärts", "start": "2099-07-02T10:00:00", "end": "2099-07-01T10:00:00", "all_day": False})
    assert bad.status_code == 422


def test_hub_calendar_delete_own_event(client):
    a, b = _auth(client, "hub_cal_del_a"), _auth(client, "hub_cal_del_b")
    ev = client.post("/api/calendar/events", headers=a, json={
        "title": "Weg damit", "start": "2099-01-01T10:00:00", "end": "2099-01-01T11:00:00", "all_day": False}).json()
    assert client.delete(f"/api/calendar/events/{ev['id']}", headers=b).status_code == 204  # partners manage the family calendar
    assert client.delete(f"/api/calendar/events/{ev['id']}", headers=a).status_code == 404


def test_built_in_sources_are_plugins_that_can_be_switched_off(client, monkeypatch):
    from app.config import settings

    h = _auth(client, "hub_off")
    ids = {p["id"] for p in client.get("/api/modules", headers=h).json()["plugins"]}
    assert {"hub_tasks", "hub_shopping", "hub_calendar"} <= ids
    monkeypatch.setattr(settings, "plugins_disabled", "hub_tasks,hub_calendar")
    assert "hub_tasks" not in {p["id"] for p in client.get("/api/tasks/providers", headers=h).json()["items"]}


def test_events_for_a_given_range_include_the_past(client):
    h = _auth(client, "hub_cal_range")
    client.post("/api/calendar/events", headers=h, json={
        "title": "Vergangen", "start": "2030-01-03T10:00:00", "end": "2030-01-03T11:00:00", "all_day": False})
    client.post("/api/calendar/events", headers=h, json={
        "title": "Ferien", "start": "2029-12-28", "end": "2030-01-06", "all_day": True})
    jan = client.get("/api/calendar/events", params={"start": "2030-01-01", "days": 31}, headers=h).json()
    titles = {e["title"] for e in jan}
    assert {"Vergangen", "Ferien"} <= titles  # multi-day event that started before the range is included
    feb = client.get("/api/calendar/events", params={"start": "2030-02-01", "days": 28}, headers=h).json()
    assert "Vergangen" not in {e["title"] for e in feb}
    assert client.get("/api/calendar/events", params={"start": "kaputt"}, headers=h).status_code == 422
