"""#47: persönliche Bindungen; Nextcloud bleibt unabhängig."""
from unittest.mock import patch

import pytest
import respx

from app.core.crypto import encrypt
from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.models.caldav import CalDAVAccount, TaskList
from tests.test_household import HouseholdCalendar, _household_user
from tests.test_tasks_caldav import FakeDAVClient, FakePrincipal


@pytest.fixture()
def mixed(client, monkeypatch):
    a, b = (_household_user(f"habitica-{name}") for name in ("a", "b"))
    from app.models.habitica import HabiticaAccount
    remote_user = "88888888-8888-4888-8888-888888888888"
    monkeypatch.setenv("HABITICA_URL", "https://habitica.example")
    monkeypatch.setenv("HABITICA_NATIVE_WRITE_ACCOUNTS", f"https://habitica.example|{remote_user}")
    with SessionLocal() as db:
        db.query(HabiticaAccount).filter(HabiticaAccount.user_id.in_([a.id, b.id])).delete()
        db.add(HabiticaAccount(user_id=a.id, server_url="https://habitica.example", remote_user_id=remote_user, api_key_enc=encrypt("mixed-test-key")))
        db.commit()
    calendars = [HouseholdCalendar(name, ["VTODO"]) for name in ("own-a", "own-b", "family")]
    # Nextcloud exposes shares through per-user URLs; objects are shared, credentials aren't.
    clients = {}
    with SessionLocal() as db:
        for user in (a, b):
            db.add(CalDAVAccount(user_id=user.id, url="https://cloud.example/dav",
                                username=user.username, password_enc=encrypt("caldav-test")))
            visible = []
            for index, original in enumerate(calendars):
                alias = HouseholdCalendar(f"{user.username}-{index}", ["VTODO"])
                alias._todos_data = original._todos_data
                # A real delete changes the remote calendar, not just its wrapper.
                lookup = alias.todo_by_uid
                def find(uid, lookup=lookup, alias=alias):
                    todo = lookup(uid)
                    if todo:
                        def delete():
                            alias._todos_data[:] = [data for data in alias._todos_data if f"UID:{uid}\r\n" not in data]
                            alias._todos_objects.pop(uid, None)
                        todo.delete = delete
                    return todo
                alias.todo_by_uid = find
                visible.append(alias)
                db.add(TaskList(user_id=user.id, caldav_url=alias.url,
                                display_name=f"Liste {index}", kind="family" if index == 2 else "personal",
                                owner_user_id=None if index == 2 else (a, b)[index].id))
            fake = FakeDAVClient("https://cloud.example/dav", user.username, "caldav-test")
            fake._principal = FakePrincipal(visible)
            clients[user.username] = fake
        db.commit()
    headers = [{"Authorization": f"Bearer {create_access_token({'sub': user.username})}"} for user in (a, b)]
    with patch("caldav.DAVClient", side_effect=lambda **kw: clients[kw['username']]):
        yield a, b, headers, calendars


def test_mixed_nextcloud_crud_never_scores_unbound_tasks(client, mixed):
    a, b, (ha, hb), calendars = mixed
    with respx.mock(using="httpx") as http, patch("app.services.habitica.score_up") as score:
        http.route(host="testserver").pass_through()
        for actor, other, headers, target in [(a, b, ha, None), (b, a, hb, None),
                                              (a, b, ha, "family"), (b, a, hb, "family"),
                                              (a, b, ha, b.id), (b, a, hb, a.id)]:
            payload = {"title": "Unabhängig"}
            if target == "family":
                payload["list"] = "family"
            elif target:
                payload["assignee_id"] = target
            response = client.post("/api/tasks", headers=headers, json=payload)
            assert response.status_code == 201, response.text
            task = response.json()
            uid = task["uid"]
            created = [data for calendar in calendars for data in calendar._todos_data if f"UID:{uid}\r\n" in data]
            assert created and all("X-FAMILIENHUB-HABITICA" not in data for data in created)
            for view in ("", "?provider=all"):
                assert client.get(f"/api/tasks{view}", headers=headers).status_code == 200
            assert client.patch(f"/api/tasks/{uid}", headers=headers, json={"title": "Geändert", "notes": "Notiz"}).status_code == 200
            assert client.post(f"/api/tasks/{uid}/complete", headers=headers).status_code == 200
            assert client.delete(f"/api/tasks/{uid}", headers=headers).status_code == 204
        score.assert_not_called()
        assert not [call for call in http.calls if call.request.url.host != "testserver"]
    assert not any(calendar._todos_data for calendar in calendars)



def test_nextcloud_legacy_opt_in_cannot_score_native_account(client, mixed):
    a, _, (headers, _), _ = mixed
    with patch("app.services.habitica.score_up") as score:
        made = client.post("/api/tasks", headers=headers, json={"title": "Dienst", "list": "family", "due": "2026-11-01",
                          "recurrence": "weekly", "rotation": [a.id], "habitica": True})
        assert made.status_code == 201, made.text
        response = client.post(f"/api/tasks/{made.json()['uid']}/complete", headers=headers)
        assert response.status_code == 200, response.text
        score.assert_not_called()
