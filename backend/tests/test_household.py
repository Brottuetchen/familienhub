"""Haushaltsrotation über echte VTODO-Operationen mit Fake-CalDAV."""
from unittest.mock import patch

import pytest

from app.core.crypto import encrypt
from app.core.database import SessionLocal
from app.models.caldav import CalDAVAccount, TaskList
from tests.test_tasks_caldav import (
    FakeCalendar, FakeDAVClient, FakePrincipal,
)


def _household_user(name):
    from types import SimpleNamespace
    from app.models.user import User
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == name).first()
        if not user:
            user = User(username=name, email=f"{name}@example.com", hashed_password="unused", role="partner")
            db.add(user)
            db.commit()
        db.query(CalDAVAccount).filter(CalDAVAccount.user_id == user.id).delete()
        db.query(TaskList).filter(TaskList.user_id == user.id).delete()
        db.commit()
        return SimpleNamespace(id=user.id, username=user.username)


@pytest.fixture()
def user_a():
    return _household_user("household-a")


@pytest.fixture()
def user_b():
    return _household_user("household-b")


@pytest.fixture()
def auth_a(user_a):
    from app.core.security import create_access_token
    return {"Authorization": f"Bearer {create_access_token({'sub': user_a.username})}"}


@pytest.fixture()
def auth_b(user_b):
    from app.core.security import create_access_token
    return {"Authorization": f"Bearer {create_access_token({'sub': user_b.username})}"}


class HouseholdCalendar(FakeCalendar):
    def todo_by_uid(self, uid):
        todo = super().todo_by_uid(uid)
        if todo:
            def complete():
                # caldav schreibt einen typisierten UTC-Zeitpunkt, keinen Python-String.
                from datetime import datetime, timezone
                comp = todo.icalendar_component
                for name in ("status", "completed", "percent-complete"):
                    comp.pop(name, None)
                comp.add("status", "COMPLETED")
                comp.add("completed", datetime.now(timezone.utc))
                comp.add("percent-complete", 100)
                todo.save()
            todo.complete = complete
        return todo


@pytest.fixture()
def household(client, auth_a, auth_b, user_a, user_b):
    calendar = HouseholdCalendar("household", ["VTODO"])
    with SessionLocal() as db:
        db.query(TaskList).filter(TaskList.caldav_url == calendar.url).delete()
        db.add(CalDAVAccount(user_id=user_a.id, url="https://cloud.example.com/dav",
                             username="a", password_enc=encrypt("secret")))
        db.add(TaskList(user_id=user_a.id, caldav_url=calendar.url,
                        display_name="Haushalt", kind="family"))
        db.commit()
    fake = FakeDAVClient("https://cloud.example.com/dav", "a", "secret")
    fake._principal = FakePrincipal([calendar])
    with patch("caldav.DAVClient", return_value=fake):
        yield calendar


def test_household_rotates_and_creates_successor_only_once(client, auth_a, user_a, user_b, household):
    response = client.post("/api/tasks", headers=auth_a, json={
        "title": "Müll rausbringen", "due": "2026-10-16", "list": "family",
        "recurrence": "weekly", "rotation": [user_a.id, user_b.id],
    })
    assert response.status_code == 201, response.text
    task = response.json()
    assert task["rotation"] == [user_a.id, user_b.id]
    assert task["assignee"] == user_a.id
    with patch("app.services.habitica.score_up") as score:
        for _ in range(2):
            completed = client.post(f"/api/tasks/{task['uid']}/complete", headers=auth_a)
            assert completed.status_code == 200, completed.text
        score.assert_not_called()  # Haushalt: Belohnung ist explizit optional.
    tasks = client.get("/api/tasks?view=family&include_done=true", headers=auth_a).json()["items"]
    assert len(tasks) == 2
    successor = next(t for t in tasks if not t["done"])
    assert successor["assignee"] == user_b.id
    assert successor["due"].startswith("2026-10-23")
    client.post(f"/api/tasks/{successor['uid']}/complete", headers=auth_a)
    tasks = client.get("/api/tasks?view=family&include_done=true", headers=auth_a).json()["items"]
    assert len(tasks) == 3
    assert next(t for t in tasks if not t["done"])["assignee"] == user_a.id


@pytest.mark.parametrize("changes", [
    {"title": "   "}, {"due": None}, {"due": "not-a-date"},
    {"recurrence": "yearly"}, {"recurrence": "none"},
    {"rotation": []}, {"rotation": [999999]}, {"rotation": [1, 1]},
    {"list": None}, {"assignee_id": 999999}, {"rotation": [True]},
])
def test_household_rejects_invalid_input(client, auth_a, user_a, household, changes):
    data = {"title": "Dienst", "due": "2026-10-16", "list": "family",
            "recurrence": "weekly", "rotation": [user_a.id]}
    data.update(changes)
    response = client.post("/api/tasks", headers=auth_a, json=data)
    assert response.status_code == 422, response.text
    assert not household._todos_data


def _member(role):
    from app.core.security import create_access_token
    from app.models.user import User
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == f"household-{role}").first()
        if not user:
            user = User(username=f"household-{role}", email=f"{role}@example.com",
                        role=role, hashed_password="unused", is_active=True)
            db.add(user)
            db.commit()
        return user.id, {"Authorization": f"Bearer {create_access_token({'sub': user.username})}"}


@pytest.mark.parametrize("role", ["child", "guest"])
def test_household_only_adults_can_create(client, household, user_a, role):
    _, headers = _member(role)
    response = client.post("/api/tasks", headers=headers, json={
        "title": "Dienst", "due": "2026-10-16", "list": "family",
        "recurrence": "weekly", "rotation": [user_a.id]})
    assert response.status_code == 403


def test_household_opt_in_scores_once_without_blocking_on_failure(client, auth_a, user_a, household):
    from unittest.mock import AsyncMock
    task = client.post("/api/tasks", headers=auth_a, json={
        "title": "Dienst", "due": "2026-10-16", "list": "family",
        "recurrence": "weekly", "rotation": [user_a.id], "habitica": True}).json()
    with patch("app.services.habitica.score_up", new_callable=AsyncMock,
               side_effect=RuntimeError("offline")) as score:
        for _ in range(2):
            assert client.post(f"/api/tasks/{task['uid']}/complete", headers=auth_a).status_code == 200
        score.assert_not_called()  # #47: Nextcloud und Habitica sind unabhängige Provider.


def test_household_shared_alias_completion_is_idempotent(client, auth_a, auth_b, user_a, user_b, household):
    task = client.post("/api/tasks", headers=auth_a, json={
        "title": "Dienst", "due": "2026-10-16", "list": "family",
        "recurrence": "weekly", "rotation": [user_a.id, user_b.id]}).json()
    assert client.post(f"/api/tasks/{task['uid']}/complete", headers=auth_a).status_code == 200
    alias = HouseholdCalendar("shared-household", ["VTODO"])
    alias._todos_data = household._todos_data
    with SessionLocal() as db:
        db.add(CalDAVAccount(user_id=user_b.id, url="https://cloud.example.com/dav", username="b", password_enc=encrypt("secret")))
        db.add(TaskList(user_id=user_b.id, caldav_url=alias.url, display_name="Haushalt", kind="family"))
        db.commit()
    fake = FakeDAVClient("https://cloud.example.com/dav", "b", "secret")
    fake._principal = FakePrincipal([alias])
    with patch("caldav.DAVClient", return_value=fake):
        response = client.post(f"/api/tasks/{task['uid']}/complete", headers=auth_b)
    assert response.status_code == 200, response.text
    assert len(household._todos_data) == 2


def test_household_successor_failure_is_retryable(client, auth_a, user_a, household):
    task = client.post("/api/tasks", headers=auth_a, json={
        "title": "Dienst", "due": "2026-10-16", "list": "family",
        "recurrence": "weekly", "rotation": [user_a.id]}).json()
    with patch.object(household, "save_todo", side_effect=ConnectionError("offline")):
        response = client.post(f"/api/tasks/{task['uid']}/complete", headers=auth_a)
    assert response.status_code == 503, response.text
    assert household.todo_by_uid(task["uid"]).icalendar_component.get("status") == "NEEDS-ACTION"
    assert client.post(f"/api/tasks/{task['uid']}/complete", headers=auth_a).status_code == 200
    assert len(household._todos_data) == 2


@pytest.mark.parametrize("operation", ["complete", "patch", "delete"])
def test_household_child_cannot_manage_others_task(client, auth_a, user_a, household, operation):
    child_id, headers = _member("child")
    task = client.post("/api/tasks", headers=auth_a, json={
        "title": "Dienst", "due": "2026-10-16", "list": "family",
        "recurrence": "weekly", "rotation": [user_a.id]}).json()
    # Kind hat eigenen CalDAV-Zugang zur Familienliste, nie Erwachsenen-Zugang ausleihen.
    with SessionLocal() as db:
        db.query(CalDAVAccount).filter(CalDAVAccount.user_id == child_id).delete()
        db.query(TaskList).filter(TaskList.user_id == child_id).delete()
        db.query(TaskList).filter(TaskList.caldav_url == household.url).update({"user_id": child_id})
        db.add(CalDAVAccount(user_id=child_id, url="https://cloud.example.com/dav", username="child", password_enc=encrypt("secret")))
        db.commit()
    path = f"/api/tasks/{task['uid']}"
    if operation == "complete":
        response = client.post(f"{path}/complete", headers=headers)
    elif operation == "patch":
        response = client.patch(path, headers=headers, json={"title": "changed"})
    else:
        response = client.delete(path, headers=headers)
    assert response.status_code == 403, response.text


def test_household_weekly_keeps_local_time_across_dst(client, auth_a, user_a, household):
    task = client.post("/api/tasks", headers=auth_a, json={
        "title": "Dienst", "due": "2026-10-21T09:00:00+02:00", "list": "family",
        "recurrence": "weekly", "rotation": [user_a.id]}).json()
    assert client.post(f"/api/tasks/{task['uid']}/complete", headers=auth_a).status_code == 200
    tasks = client.get("/api/tasks?view=family", headers=auth_a).json()["items"]
    assert next(t for t in tasks if not t["done"])["due"] == "2026-10-28T09:00:00+01:00"


@pytest.mark.parametrize("configuration,status", [("account", 409), ("list", 409), ("offline", 503)])
def test_household_create_configuration_and_outage_errors(client, auth_a, user_a, household, configuration, status):
    with SessionLocal() as db:
        if configuration == "account":
            db.query(CalDAVAccount).filter(CalDAVAccount.user_id == user_a.id).delete()
        if configuration == "list":
            db.query(TaskList).filter(TaskList.user_id == user_a.id).delete()
        db.commit()
    with patch.object(household, "save_todo", side_effect=ConnectionError("offline")):
        response = client.post("/api/tasks", headers=auth_a, json={
            "title": "Dienst", "due": "2026-10-16", "list": "family",
            "recurrence": "weekly", "rotation": [user_a.id]})
    assert response.status_code == status, response.text


def test_household_date_only_remains_date_only(client, auth_a, user_a, household):
    task = client.post("/api/tasks", headers=auth_a, json={
        "title": "Dienst", "due": "2026-01-31", "list": "family",
        "recurrence": "monthly", "rotation": [user_a.id]}).json()
    assert task["due"] == "2026-01-31"
    assert client.post(f"/api/tasks/{task['uid']}/complete", headers=auth_a).status_code == 200
    tasks = client.get("/api/tasks?view=family", headers=auth_a).json()["items"]
    assert next(t for t in tasks if not t["done"])["due"] == "2026-02-28"


def test_household_retries_after_successor_saved_but_completion_failed(client, auth_a, user_a, household):
    task = client.post("/api/tasks", headers=auth_a, json={
        "title": "Dienst", "due": "2026-10-16", "list": "family",
        "recurrence": "weekly", "rotation": [user_a.id]}).json()
    original_lookup = household.todo_by_uid
    def lookup(uid):
        todo = original_lookup(uid)
        if uid == task["uid"]:
            def fail():
                raise ConnectionError("complete failed")
            todo.complete = fail
        return todo
    with patch.object(household, "todo_by_uid", side_effect=lookup):
        assert client.post(f"/api/tasks/{task['uid']}/complete", headers=auth_a).status_code == 503
    assert len(household._todos_data) == 2
    assert client.post(f"/api/tasks/{task['uid']}/complete", headers=auth_a).status_code == 200
    assert len(household._todos_data) == 2


def test_household_concurrent_completion_has_one_successor(client, auth_a, user_a, household):
    from concurrent.futures import ThreadPoolExecutor
    from unittest.mock import AsyncMock
    task = client.post("/api/tasks", headers=auth_a, json={
        "title": "Dienst", "due": "2026-10-16", "list": "family",
        "recurrence": "weekly", "rotation": [user_a.id], "habitica": True}).json()
    with patch("app.services.habitica.score_up", new_callable=AsyncMock) as score:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: client.post(f"/api/tasks/{task['uid']}/complete", headers=auth_a), range(2)))
        assert [r.status_code for r in responses] == [200, 200]
        score.assert_not_called()  # #47: keine implizite providerübergreifende Belohnung.
    assert len(household._todos_data) == 2


def test_household_skips_inactive_rotation_member(client, auth_a, user_a, user_b, household):
    from app.models.user import User
    task = client.post("/api/tasks", headers=auth_a, json={
        "title": "Dienst", "due": "2026-10-16", "list": "family",
        "recurrence": "weekly", "rotation": [user_a.id, user_b.id]}).json()
    with SessionLocal() as db:
        db.get(User, user_b.id).is_active = False
        db.commit()
    try:
        assert client.post(f"/api/tasks/{task['uid']}/complete", headers=auth_a).status_code == 200
        tasks = client.get("/api/tasks?view=family", headers=auth_a).json()["items"]
        assert next(t for t in tasks if not t["done"])["assignee"] == user_a.id
    finally:
        with SessionLocal() as db:
            db.get(User, user_b.id).is_active = True
            db.commit()


@pytest.mark.parametrize("changes,stored", [
    ({"due": ""}, {}),
    ({"due": "not-a-date"}, {}),
    ({"title": "   "}, {}),
    ({"title": "x" * 201}, {}),
    ({"notes": "changed"}, {"summary": " "}),
    ({"notes": "changed"}, {"summary": "x" * 201}),
    ({"title": "changed"}, {"due": None}),
])
def test_household_patch_rejects_invalid_effective_values_without_mutation(
    client, auth_a, user_a, household, changes, stored,
):
    task = client.post("/api/tasks", headers=auth_a, json={
        "title": "Dienst", "due": "2026-10-16", "list": "family",
        "recurrence": "weekly", "rotation": [user_a.id]}).json()
    todo = household.todo_by_uid(task["uid"])
    comp = todo.icalendar_component
    for name, value in stored.items():
        comp.pop(name, None)
        if value is not None:
            comp.add(name, value)
    before = comp.to_ical()
    saved = list(household._todos_data)
    with patch.object(todo, "save", wraps=todo.save) as save:
        response = client.patch(f"/api/tasks/{task['uid']}", headers=auth_a,
                                json={"notes": "must not change", **changes})
    assert response.status_code == 422, response.text
    save.assert_not_called()
    assert comp.to_ical() == before
    assert household._todos_data == saved


@pytest.mark.parametrize("due,expected,successor", [
    ("2026-10-21", "2026-10-21", "2026-10-28"),
    ("2026-10-21T09:00:00+02:00", "2026-10-21T09:00:00+02:00", "2026-10-28T09:00:00+01:00"),
    ("2026-10-21T09:00:00", "2026-10-21T09:00:00+02:00", "2026-10-28T09:00:00+01:00"),
    ("2026-10-21T07:00:00Z", "2026-10-21T09:00:00+02:00", "2026-10-28T09:00:00+01:00"),
])
def test_household_patch_serializes_due_and_preserves_properties(
    client, auth_a, user_a, household, due, expected, successor,
):
    from datetime import date, datetime
    from icalendar import Calendar
    from app.core.timeutil import local_tz

    task = client.post("/api/tasks", headers=auth_a, json={
        "title": "Dienst", "due": "2026-10-16", "list": "family",
        "recurrence": "weekly", "rotation": [user_a.id]}).json()
    todo = household.todo_by_uid(task["uid"])
    comp = todo.icalendar_component
    comp.add("x-apple-sort-order", "12345")
    comp.add("categories", ["Haushalt", "Woche"])
    todo.save()
    unknown = {name: comp[name].to_ical() for name in ("x-apple-sort-order", "categories")}
    response = client.patch(f"/api/tasks/{task['uid']}", headers=auth_a, json={"due": due})
    assert response.status_code == 200, response.text
    assert response.json()["due"] == expected
    saved = Calendar.from_ical(household._todos_data[0]).walk("VTODO")[0]
    assert not saved.errors
    assert saved["due"].dt.isoformat() == expected
    assert type(saved["due"].dt) is (date if len(due) == 10 else datetime)
    if len(due) != 10:
        assert saved["due"].params["TZID"] == str(local_tz())
    for name, value in unknown.items():
        assert saved[name].to_ical() == value
    assert client.post(f"/api/tasks/{task['uid']}/complete", headers=auth_a).status_code == 200
    tasks = client.get("/api/tasks?view=family", headers=auth_a).json()["items"]
    assert next(t for t in tasks if not t["done"])["due"] == successor


@pytest.mark.parametrize("failure", ["connection", "caldav_permission", "permission"])
def test_household_delete_write_failure_is_retryable(
    client, auth_a, user_a, household, caplog, failure,
):
    from caldav.lib.error import AuthorizationError

    task = client.post("/api/tasks", headers=auth_a, json={
        "title": "Dienst", "due": "2026-10-16", "list": "family",
        "recurrence": "weekly", "rotation": [user_a.id]}).json()
    todo = household.todo_by_uid(task["uid"])
    error = {"connection": ConnectionError("offline"),
             "caldav_permission": AuthorizationError("403 Forbidden"),
             "permission": PermissionError("write denied")}[failure]
    before = list(household._todos_data)
    with patch.object(todo, "delete", side_effect=error):
        response = client.delete(f"/api/tasks/{task['uid']}", headers=auth_a)
    assert response.status_code == 503, response.text
    assert household._todos_data == before
    assert any(record.levelname == "WARNING" and record.exc_info
               and "delete_task failed" in record.message for record in caplog.records)
    # Fachsystem-Delete ist der einzige Schreibzugriff; beim Retry genau dieses Objekt entfernen.
    with patch.object(todo, "delete", side_effect=lambda: household._todos_data.clear()) as delete:
        response = client.delete(f"/api/tasks/{task['uid']}", headers=auth_a)
    assert response.status_code == 204, response.text
    delete.assert_called_once()
    assert not household._todos_data


def test_household_delete_discovery_failure_is_retryable(client, auth_a, user_a, household, caplog):
    task = client.post("/api/tasks", headers=auth_a, json={
        "title": "Dienst", "due": "2026-10-16", "list": "family",
        "recurrence": "weekly", "rotation": [user_a.id]}).json()
    todo = household.todo_by_uid(task["uid"])
    before = list(household._todos_data)
    with patch.object(household, "get_supported_components", side_effect=ConnectionError("offline")):
        response = client.delete(f"/api/tasks/{task['uid']}", headers=auth_a)
        assert response.status_code == 503, response.text
        assert household._todos_data == before
        assert client.get("/api/tasks?view=family", headers=auth_a).json()["items"] == []
    assert any(record.levelname == "WARNING" and record.exc_info
               and "delete_task failed" in record.message for record in caplog.records)
    with patch.object(todo, "delete", side_effect=lambda: household._todos_data.clear()) as delete:
        assert client.delete(f"/api/tasks/{task['uid']}", headers=auth_a).status_code == 204
    delete.assert_called_once()
    assert not household._todos_data


@pytest.mark.parametrize("missing", ["none", "not_found", "no_lists"])
def test_household_delete_absent_task_returns_404(client, auth_a, user_a, household, missing):
    from caldav.lib.error import NotFoundError

    if missing == "no_lists":
        with SessionLocal() as db:
            db.query(TaskList).filter(TaskList.user_id == user_a.id).delete()
            db.commit()
    error = NotFoundError("absent") if missing == "not_found" else None
    with patch.object(household, "todo_by_uid", return_value=None, side_effect=error):
        response = client.delete("/api/tasks/absent", headers=auth_a)
    assert response.status_code == 404, response.text


@pytest.mark.parametrize("configured", [True, False])
def test_household_delete_healthy_calendar_survives_sibling_discovery_failure(
    client, auth_a, user_a, household, configured,
):
    task = client.post("/api/tasks", headers=auth_a, json={
        "title": "Dienst", "due": "2026-10-16", "list": "family",
        "recurrence": "weekly", "rotation": [user_a.id]}).json()
    sibling = HouseholdCalendar("unavailable-sibling", ["VTODO"])
    if configured:
        with SessionLocal() as db:
            db.add(TaskList(user_id=user_a.id, caldav_url=sibling.url,
                            display_name="Andere Liste", kind="family"))
            db.commit()
    fake = FakeDAVClient("https://cloud.example.com/dav", "a", "secret")
    fake._principal = FakePrincipal([sibling, household])
    with patch("caldav.DAVClient", return_value=fake), patch.object(
        sibling, "get_supported_components", side_effect=ConnectionError("offline"),
    ):
        tasks = client.get("/api/tasks?view=family", headers=auth_a).json()["items"]
        assert [item["uid"] for item in tasks] == [task["uid"]]
        todo = household.todo_by_uid(task["uid"])
        with patch.object(todo, "delete", side_effect=lambda: household._todos_data.clear()) as delete:
            assert client.delete(f"/api/tasks/{task['uid']}", headers=auth_a).status_code == 204
        response = client.delete("/api/tasks/absent", headers=auth_a)
        assert response.status_code == (503 if configured else 404), response.text
    delete.assert_called_once()
    assert not household._todos_data
