"""Native Providerpfade mit echtem Router und Habitica-HTTP-Fake."""
import json
from uuid import uuid4

import httpx
import pytest
import respx

from app.core.database import SessionLocal
from app.core.crypto import encrypt
from app.core.security import create_access_token
from app.models.habitica import HabiticaAccount
from tests.test_household import _household_user

REMOTE_USER = "33333333-3333-4333-8333-333333333334"
REMOTE_TASK = "11111111-1111-4111-8111-111111111111"


@pytest.fixture()
def native(client, monkeypatch):
    monkeypatch.setenv("HABITICA_URL", "https://habitica.example")
    monkeypatch.setenv("HABITICA_NATIVE_WRITE_ACCOUNTS", f"https://habitica.example|{REMOTE_USER}")
    user = _household_user("native-provider")
    with SessionLocal() as db:
        account = db.get(HabiticaAccount, user.id)
        if not account:
            account = HabiticaAccount(user_id=user.id)
            db.add(account)
        account.server_url = "https://habitica.example"
        account.remote_user_id = REMOTE_USER
        account.api_key_enc = encrypt("test-native-key")
        account.pending_operation = None
        db.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': user.username})}"}
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        providers = client.get("/api/tasks/providers", headers=headers).json()["items"]
        provider = next((p for p in providers if p["id"] == "habitica"), None)
        assert provider is not None, providers
        yield user, headers, http, f"provider=habitica&account={provider['account']}"


def test_habitica_only_select_refresh_create_and_minimal_edit(client, native):
    user, headers, http, query = native
    task = {"id": REMOTE_TASK, "userId": REMOTE_USER, "type": "daily", "text": "Original",
            "updatedAt": "v1", "repeat": {"m": True}, "futureField": {"keep": True}, "checklist": []}
    def response(request):
        nonlocal task
        if request.method == "PUT":
            body = json.loads(request.content)
            assert body == {"text": "Neuer Titel"}
            task = {**task, **body, "updatedAt": "v2"}
        return httpx.Response(200, json={"success": True, "data": task})
    http.route(path=f"/api/v3/tasks/{REMOTE_TASK}").mock(side_effect=response)
    http.get("https://habitica.example/api/v3/tasks/user").respond(200, json={"success": True, "data": [task]})
    assert client.get("/api/habitica/tasks", headers=headers).json()["items"][0]["uid"] == REMOTE_TASK
    assert client.get(f"/api/tasks?{query}", headers=headers).json()["items"] == []
    selected = client.put(f"/api/tasks/{REMOTE_TASK}/selection?{query}", headers=headers, json={"selected": True})
    assert selected.status_code == 200, selected.text
    listed = client.get(f"/api/tasks?{query}", headers=headers).json()["items"][0]
    assert listed["native"]["futureField"] == {"keep": True}
    task["text"] = "Extern geändert"
    assert client.get(f"/api/tasks?{query}", headers=headers).json()["items"][0]["title"] == "Extern geändert"
    updated = client.patch(f"/api/tasks/{REMOTE_TASK}?{query}", headers=headers,
                           json={"title": "Neuer Titel", "expected_version": "v1", "operation_id": str(uuid4())})
    assert updated.status_code == 200, updated.text
    assert updated.json()["native"]["futureField"] == {"keep": True}
    create = http.post("https://habitica.example/api/v3/tasks/user").respond(200, json={"success": True, "data": task})
    request = {"title": "Neu", "native": {"type": "daily", "frequency": "yearly", "everyX": 2}, "operation_id": str(uuid4())}
    made = client.post(f"/api/tasks?{query}", headers=headers, json=request)
    assert made.status_code == 201, made.text
    again = client.post(f"/api/tasks?{query}", headers=headers, json=request)
    assert again.status_code == 201, again.text
    assert create.call_count == 1
    assert client.get(f"/api/tasks?provider=habitica&account={user.id + 1}", headers=headers).status_code == 403


def test_legacy_namespace_cannot_be_mutated_through_nextcloud(client, native):
    _, headers, _, _ = native
    for method, suffix, payload in [("PATCH", "", {"title": "Nicht ändern"}),
                                    ("POST", "/complete", None), ("DELETE", "", None)]:
        result = client.request(method, f"/api/tasks/habitica-{REMOTE_TASK}{suffix}", headers=headers, json=payload)
        assert result.status_code == 409, result.text


@pytest.mark.parametrize("kind,direction,allowed", [("habit", "up", False), ("habit", "down", True),
                                                   ("reward", "down", False), ("reward", "up", True),
                                                   ("daily", "down", False), ("todo", "up", True)])
def test_native_score_guards_and_exact_operation_replay(client, native, kind, direction, allowed):
    _, headers, http, query = native
    remote = {"id": REMOTE_TASK, "userId": REMOTE_USER, "type": kind, "up": False, "down": True, "completed": False}
    http.get(f"https://habitica.example/api/v3/tasks/{REMOTE_TASK}").respond(200, json={"success": True, "data": remote})
    route = http.post(f"https://habitica.example/api/v3/tasks/{REMOTE_TASK}/score/{direction}")
    if allowed:
        route.respond(200, json={"success": True, "data": {"delta": 1}})
    request = {"action": direction, "operation_id": str(uuid4())}
    response = client.post(f"/api/tasks/{REMOTE_TASK}/actions?{query}", headers=headers, json=request)
    assert response.status_code == (200 if allowed else 409), response.text
    if allowed:
        assert client.post(f"/api/tasks/{REMOTE_TASK}/actions?{query}", headers=headers, json=request).status_code == 200
        assert route.call_count == 1
    else:
        assert not route.called



def test_score_timeout_blocks_restart_and_new_operation(client, native):
    _, headers, http, query = native
    remote = {"id": REMOTE_TASK, "userId": REMOTE_USER, "type": "habit", "up": True}
    http.get(f"https://habitica.example/api/v3/tasks/{REMOTE_TASK}").respond(200, json={"success": True, "data": remote})
    route = http.post(f"https://habitica.example/api/v3/tasks/{REMOTE_TASK}/score/up").mock(side_effect=httpx.ReadTimeout("after commit"))
    for _ in range(2):
        response = client.post(f"/api/tasks/{REMOTE_TASK}/actions?{query}", headers=headers,
                               json={"action": "up", "operation_id": str(uuid4())})
        assert response.status_code == 409, response.text
    assert route.call_count == 1


def test_warm_disabled_server_change_and_cutover_are_fail_closed(client, native, monkeypatch):
    _, headers, http, query = native
    from app.config import settings
    monkeypatch.setattr(settings, "plugins_disabled", "habitica")
    assert client.get(f"/api/tasks?{query}", headers=headers).status_code == 409
    monkeypatch.setattr(settings, "plugins_disabled", "")
    monkeypatch.setenv("HABITICA_URL", "https://other.example")
    assert client.get(f"/api/tasks?{query}", headers=headers).json()["status"] == "not_configured"
    monkeypatch.setenv("HABITICA_URL", "https://habitica.example")
    monkeypatch.setenv("HABITICA_NATIVE_WRITE_ACCOUNTS", "")
    response = client.post(f"/api/tasks?{query}", headers=headers, json={"title": "Gesperrt", "native": {"type": "todo"}, "operation_id": str(uuid4())})
    assert response.status_code == 409, response.text
    assert not [c for c in http.calls if c.request.url.host != "testserver"]


@pytest.mark.parametrize("kind,fields", [
    ("habit", {"up": False, "down": False, "frequency": "monthly"}),
    ("daily", {"frequency": "yearly", "everyX": 2, "startDate": "2026-01-01T00:00:00Z", "repeat": {"m": False, "su": True}, "daysOfMonth": [1, 31], "weeksOfMonth": [1, 5], "streak": 7, "collapseChecklist": True}),
    ("todo", {"date": None, "collapseChecklist": False}),
    ("reward", {"value": 15.5}),
])
def test_native_field_matrix_is_not_reduced_to_checkbox(client, native, kind, fields):
    _, headers, http, query = native
    options = {"type": kind, "notes": "Notizen", "alias": "alias", "attribute": "per", "priority": 1.5,
               "tags": ["22222222-2222-4222-8222-222222222222"],
               "reminders": [{"id": "44444444-4444-4444-8444-444444444444", "time": "2026-11-01T11:00:00Z"}], **fields}
    http.get("https://habitica.example/api/v3/user").respond(200, json={"success": True, "data": {
        "id": REMOTE_USER, "tags": [{"id": options["tags"][0], "name": "Eigenes Tag"}]}})
    def create(request):
        body = json.loads(request.content)
        assert body == {"text": "Native Aufgabe", **options}
        return httpx.Response(200, json={"success": True, "data": {**body, "id": REMOTE_TASK, "userId": REMOTE_USER}})
    route = http.post("https://habitica.example/api/v3/tasks/user").mock(side_effect=create)
    response = client.post(f"/api/tasks?{query}", headers=headers, json={"title": "Native Aufgabe", "native": options, "operation_id": str(uuid4())})
    assert response.status_code == 201, response.text
    assert route.call_count == 1


def test_ownership_and_conflict_stop_remote_writes(client, native):
    _, headers, http, query = native
    remote = {"id": REMOTE_TASK, "userId": "not-own-account", "type": "todo", "updatedAt": "v2"}
    http.get(f"https://habitica.example/api/v3/tasks/{REMOTE_TASK}").mock(side_effect=lambda r: httpx.Response(200, json={"success": True, "data": remote}))
    for method, suffix, body in [("PUT", "/selection", {"selected": True}), ("POST", "/actions", {"action": "up", "operation_id": str(uuid4())}),
                                 ("PATCH", "", {"title": "fremd", "expected_version": "v2", "operation_id": str(uuid4())}), ("DELETE", "", {"operation_id": str(uuid4())})]:
        url = f"/api/tasks/{REMOTE_TASK}{suffix}?{query}"
        if method == "DELETE": url += f"&operation_id={body['operation_id']}"
        response = client.request(method, url, headers=headers, json=body)
        assert response.status_code == 403, response.text
    remote["userId"] = REMOTE_USER
    response = client.patch(f"/api/tasks/{REMOTE_TASK}?{query}", headers=headers, json={"native": {"notes": "stale"}, "expected_version": "v1", "operation_id": str(uuid4())})
    assert response.status_code == 409
    assert not [c for c in http.calls if c.request.url.host != "testserver" and c.request.method != "GET"]


def test_native_checklist_crud_order_and_minimal_target_state(client, native):
    _, headers, http, query = native
    first, second = "55555555-5555-4555-8555-555555555555", "66666666-6666-4666-8666-666666666666"
    remote = {"id": REMOTE_TASK, "userId": REMOTE_USER, "type": "todo", "updatedAt": "v1", "checklist": [
        {"id": first, "text": "Eins", "completed": False, "linkId": "preserve", "future": 1},
        {"id": second, "text": "Zwei", "completed": True, "future": 2}]}
    http.get(f"https://habitica.example/api/v3/tasks/{REMOTE_TASK}").respond(200, json={"success": True, "data": remote})
    routes = [http.post(f"https://habitica.example/api/v3/tasks/{REMOTE_TASK}/checklist").respond(200, json={"success": True, "data": remote}),
              http.put(f"https://habitica.example/api/v3/tasks/{REMOTE_TASK}/checklist/{first}").respond(200, json={"success": True, "data": remote}),
              http.delete(f"https://habitica.example/api/v3/tasks/{REMOTE_TASK}/checklist/{first}").respond(200, json={"success": True, "data": remote}),
              http.put(f"https://habitica.example/api/v3/tasks/{REMOTE_TASK}").respond(200, json={"success": True, "data": remote})]
    for action, fields, item in [("checklist_add", {"text": "Neu"}, None), ("checklist_edit", {"completed": True}, first),
                                 ("checklist_delete", {}, first), ("checklist_move", {"position": 0}, second)]:
        response = client.post(f"/api/tasks/{REMOTE_TASK}/actions?{query}", headers=headers, json={"action": action, "fields": fields, "item_id": item, "operation_id": str(uuid4())})
        assert response.status_code == 200, response.text
    assert json.loads(routes[1].calls[0].request.content) == {"completed": True}
    assert json.loads(routes[3].calls[0].request.content) == {"checklist": [remote["checklist"][1], remote["checklist"][0]]}
    assert all(route.call_count == 1 for route in routes)


@pytest.mark.parametrize("method", ["POST", "DELETE"])
def test_ambiguous_create_delete_never_replay(client, native, method):
    _, headers, http, query = native
    remote = {"id": REMOTE_TASK, "userId": REMOTE_USER, "type": "todo"}
    http.get(f"https://habitica.example/api/v3/tasks/{REMOTE_TASK}").respond(200, json={"success": True, "data": remote})
    path = "tasks/user" if method == "POST" else f"tasks/{REMOTE_TASK}"
    route = http.request(method, f"https://habitica.example/api/v3/{path}").respond(307, headers={"location": "https://habitica.example/other"})
    for _ in range(2):
        op = str(uuid4())
        url = f"/api/tasks?{query}" if method == "POST" else f"/api/tasks/{REMOTE_TASK}?{query}&operation_id={op}"
        response = client.request(method, url, headers=headers, json={"title": "Native", "native": {"type": "todo"}, "operation_id": op})
        assert response.status_code == 409, response.text
    assert route.call_count == 1


def test_habitica_only_today_without_nextcloud_task_adapter(client, native, monkeypatch):
    _, headers, http, query = native
    from app.config import settings
    from app.connectors.nextcloud_tasks_connector import NextcloudTasksConnector
    monkeypatch.setattr(settings, "plugins_disabled", "nextcloud")
    def forbidden(*args, **kwargs): raise AssertionError("Nextcloud ist kein Habitica-Unterbau")
    monkeypatch.setattr(NextcloudTasksConnector, "__init__", forbidden)
    remote = {"id": REMOTE_TASK, "userId": REMOTE_USER, "type": "daily", "text": "Nativ", "completed": True, "isDue": False}
    http.get(f"https://habitica.example/api/v3/tasks/{REMOTE_TASK}").respond(200, json={"success": True, "data": remote})
    assert client.put(f"/api/tasks/{REMOTE_TASK}/selection?{query}", headers=headers, json={"selected": True}).status_code == 200
    response = client.get("/api/today", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["tasks"]["items"][0]["provider"] == "habitica"
    assert response.json()["tasks"]["items"][0]["native"]["isDue"] is False


def test_native_tag_references_require_own_user_options(client, native):
    _, headers, http, query = native
    foreign_tag = "77777777-7777-4777-8777-777777777777"
    http.get("https://habitica.example/api/v3/user").respond(200, json={"success": True, "data": {"id": REMOTE_USER, "tags": []}})
    create = http.post("https://habitica.example/api/v3/tasks/user").respond(200, json={"success": True, "data": {
        "id": REMOTE_TASK, "userId": REMOTE_USER, "type": "todo", "tags": [foreign_tag]}})
    response = client.post(f"/api/tasks?{query}", headers=headers, json={"title": "Keine fremden Tags", "native": {"type": "todo", "tags": [foreign_tag]}, "operation_id": str(uuid4())})
    assert response.status_code == 403, response.text
    assert not create.called


def test_native_options_expose_current_write_authority(client, native, monkeypatch):
    _, headers, http, _ = native
    http.get("https://habitica.example/api/v3/user").respond(200, json={"success": True, "data": {"id": REMOTE_USER, "tags": []}})
    assert client.get("/api/habitica/options", headers=headers).json()["writes_enabled"] is True
    monkeypatch.setenv("HABITICA_NATIVE_WRITE_ACCOUNTS", "")
    assert client.get("/api/habitica/options", headers=headers).json()["writes_enabled"] is False
