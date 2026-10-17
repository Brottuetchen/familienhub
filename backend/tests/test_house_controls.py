"""Haussteuerung: echter Router und echte HA-HTTP-Grenze, keine Gerätezugriffe."""
import json

import pytest
import respx

from app.config import settings


@pytest.fixture
def controls(monkeypatch):
    monkeypatch.setattr(settings, "homeassistant_url", "http://ha.test")
    monkeypatch.setattr(settings, "homeassistant_token", "test-token")
    monkeypatch.setitem(settings.__dict__, "ha_house_write_entities", "light.lamp")
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        yield http


def test_house_control_rechecks_state_and_posts_exact_service(client, auth, controls):
    state = controls.get("http://ha.test/api/states/light.lamp").respond(200, json={
        "entity_id": "light.lamp", "state": "off", "attributes": {"private": "secret"},
    })
    service = controls.post("http://ha.test/api/services/light/turn_on").respond(200, json=[])
    response = client.post("/api/house/actions", headers=auth,
                           json={"entity_id": "light.lamp", "action": "turn_on"})
    assert response.status_code == 200
    assert response.json() == {"accepted": True, "control": None}  # HA meldet keinen geänderten Zustand
    assert state.call_count == service.call_count == 1
    assert json.loads(service.calls.last.request.content) == {"entity_id": "light.lamp"}


@pytest.mark.parametrize("body", [
    {"entity_id": "light.other", "action": "turn_on"},
    {"entity_id": "../private", "action": "turn_on"},
    {"entity_id": "light.lamp", "action": "toggle"},
    {"entity_id": "light.lamp", "action": "turn_on", "service_data": {}},
    {"entity_id": "light.lamp", "action": "turn_on", "domain": "lock"},
    {"entity_id": "light.lamp", "action": "turn_on", "brightness": 1},
    {"entity_id": 123, "action": "turn_on"},
])
def test_house_rejects_unlisted_invalid_and_arbitrary_fields(client, auth, controls, body):
    response = client.post("/api/house/actions", headers=auth, json=body)
    assert response.status_code == 422
    assert not [c for c in controls.calls if c.request.url.host == "ha.test"]


@pytest.mark.parametrize("mode", ["empty", "disabled", "no_url", "no_token", "unsupported"])
def test_house_live_configuration_blocks_warm_session_without_ha(client, auth, controls, monkeypatch, mode):
    # auth fixture is already a warmed authenticated session.
    if mode == "empty":
        monkeypatch.setitem(settings.__dict__, "ha_house_write_entities", "")
        monkeypatch.setattr(settings, "ha_house_entities", "light.lamp")
    elif mode == "disabled":
        monkeypatch.setattr(settings, "plugins_disabled", "homeassistant")
    elif mode == "unsupported":
        monkeypatch.setitem(settings.__dict__, "ha_house_write_entities", "lock.door")
    else:
        monkeypatch.setattr(settings, "homeassistant_" + ("url" if mode == "no_url" else "token"), None)
    response = client.post("/api/house/actions", headers=auth,
                           json={"entity_id": "light.lamp", "action": "turn_on"})
    assert response.status_code in (409, 422)
    assert not [c for c in controls.calls if c.request.url.host == "ha.test"]


@pytest.mark.parametrize("role,expected", [("admin", 200), ("partner", 200), ("kind", 403), ("gast", 403)])
def test_house_roles_and_read_access(client, auth, controls, session, role, expected):
    from app.core.security import create_access_token
    from app.models.user import User
    user = User(username="house_" + role, email=role + "@house.test", role=role, is_admin=False, hashed_password="unused")
    session.add(user)
    session.commit()
    headers = {"Authorization": "Bearer " + create_access_token({"sub": user.username})}
    controls.get("http://ha.test/api/states/light.lamp").respond(200, json={
        "entity_id": "light.lamp", "state": "off", "attributes": {},
    })
    service = controls.post("http://ha.test/api/services/light/turn_on").respond(200, json=[])
    try:
        metadata = client.get("/api/house/controls", headers=headers)
        assert metadata.status_code == 200
        assert metadata.json()["items"][0]["actions"] == (["turn_on", "turn_off"] if expected == 200 else [])
        response = client.post("/api/house/actions", headers=headers,
                               json={"entity_id": "light.lamp", "action": "turn_on"})
        assert response.status_code == expected
        assert service.call_count == (1 if expected == 200 else 0)
    finally:
        session.delete(user)
        session.commit()


def test_house_requires_auth_and_rejects_query_parameters(client, auth, controls):
    assert client.get("/api/house/controls").status_code == 401
    assert client.post("/api/house/actions", json={"entity_id": "light.lamp", "action": "turn_on"}).status_code == 401
    assert client.post("/api/house/actions?service=toggle", headers=auth,
                       json={"entity_id": "light.lamp", "action": "turn_on"}).status_code == 422


@pytest.mark.parametrize("entity,action,brightness,attrs,service,body", [
    ("switch.plug", "turn_off", None, {}, "switch/turn_off", {"entity_id": "switch.plug"}),
    ("script.evening", "activate", None, {}, "script/turn_on", {"entity_id": "script.evening"}),
    ("scene.evening", "activate", None, {}, "scene/turn_on", {"entity_id": "scene.evening"}),
    ("light.lamp", "brightness", 128, {"supported_color_modes": ["brightness"]}, "light/turn_on", {"entity_id": "light.lamp", "brightness": 128}),
])
def test_house_supported_actions_exact_http(client, auth, controls, monkeypatch, entity, action, brightness, attrs, service, body):
    monkeypatch.setattr(settings, "ha_house_write_entities", entity)
    controls.get("http://ha.test/api/states/" + entity).respond(200, json={
        "entity_id": entity, "state": "off", "attributes": attrs,
    })
    post = controls.post("http://ha.test/api/services/" + service).respond(200, json=[])
    data = {"entity_id": entity, "action": action}
    if brightness is not None:
        data["brightness"] = brightness
    assert client.post("/api/house/actions", headers=auth, json=data).status_code == 200
    assert post.call_count == 1 and json.loads(post.calls.last.request.content) == body


@pytest.mark.parametrize("brightness", [-1, 256, 1.5, True, "10", None])
def test_house_strict_brightness_bounds(client, auth, controls, brightness):
    response = client.post("/api/house/actions", headers=auth,
                           json={"entity_id": "light.lamp", "action": "brightness", "brightness": brightness})
    assert response.status_code == 422
    assert not [c for c in controls.calls if c.request.url.host == "ha.test"]


@pytest.mark.parametrize("attrs", [{}, {"supported_color_modes": ["onoff"]}, {"supported_color_modes": ["unknown"]}])
def test_house_cannot_dim_without_actual_capability(client, auth, controls, attrs):
    controls.get("http://ha.test/api/states/light.lamp").respond(200, json={
        "entity_id": "light.lamp", "state": "off", "attributes": attrs,
    })
    response = client.post("/api/house/actions", headers=auth,
                           json={"entity_id": "light.lamp", "action": "brightness", "brightness": 128})
    assert response.status_code == 422
    assert not [c for c in controls.calls if c.request.method == "POST" and c.request.url.host == "ha.test"]


@pytest.mark.parametrize("raw,status", [
    ({"entity_id": "light.lamp", "state": "unknown"}, 200),
    ({"entity_id": "light.lamp", "state": "unavailable"}, 200),
    ({"entity_id": "light.lamp"}, 200),
    ({"entity_id": "light.lamp", "state": "weird"}, 200),
    ({"entity_id": "light.other", "state": "on"}, 200),
    ({}, 404), ({}, 503),
])
def test_house_unavailable_state_blocks_write(client, auth, controls, raw, status):
    controls.get("http://ha.test/api/states/light.lamp").respond(status, json=raw)
    response = client.post("/api/house/actions", headers=auth,
                           json={"entity_id": "light.lamp", "action": "turn_on"})
    assert response.status_code == 409
    assert "http://" not in response.text and "test-token" not in response.text
    assert not [c for c in controls.calls if c.request.method == "POST" and c.request.url.host == "ha.test"]


@pytest.mark.parametrize("failure", ["timeout", "503", "redirect"])
def test_house_ambiguous_service_failure_never_repeats(client, auth, controls, failure):
    import httpx
    controls.get("http://ha.test/api/states/light.lamp").respond(200, json={
        "entity_id": "light.lamp", "state": "on", "attributes": {},
    })
    post = controls.post("http://ha.test/api/services/light/turn_on")
    if failure == "timeout":
        post.mock(side_effect=httpx.ReadTimeout("private-url-token"))
    elif failure == "redirect":
        post.respond(307, headers={"Location": "http://ha.test/api/services/light/turn_on"})
    else:
        post.respond(503, json={"private": "secret"})
    response = client.post("/api/house/actions", headers=auth,
                           json={"entity_id": "light.lamp", "action": "turn_on"})
    assert response.status_code == 409
    assert "private" not in response.text
    assert post.call_count == 1


def test_house_controls_safe_metadata_and_fresh_capability(client, auth, controls):
    state = controls.get("http://ha.test/api/states/light.lamp").respond(200, json={
        "entity_id": "light.lamp", "state": "on", "attributes": {
            "friendly_name": "Lampe", "brightness": 99, "supported_color_modes": ["rgb"], "private": "secret",
        },
    })
    response = client.get("/api/house/controls", headers=auth)
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"status": "ok", "error": None, "items": [{
        "entity_id": "light.lamp", "name": "Lampe", "state": "on",
        "actions": ["turn_on", "turn_off", "brightness"], "brightness": 99,
    }]}
    state.respond(200, json={"entity_id": "light.lamp", "state": "unavailable"})
    data = client.get("/api/house/controls", headers=auth).json()
    assert data["items"][0]["actions"] == [] and data["items"][0]["state"] is None


@pytest.mark.parametrize("value", ["lock.door", "Light.lamp", "light.lamp/other", ",".join(f"light.l{i}" for i in range(7))])
def test_house_admin_validates_write_selection_atomically(client, auth, controls, value):
    before = settings.ha_house_write_entities
    assert client.put("/api/admin/settings", headers=auth, json={"values": {"HA_HOUSE_WRITE_ENTITIES": value}}).status_code == 422
    assert settings.ha_house_write_entities == before


def test_house_write_admin_live_removal_before_post(client, auth, controls, session):
    from app.models.config import ConfigOverride
    try:
        assert client.put("/api/admin/settings", headers=auth, json={"values": {"HA_HOUSE_WRITE_ENTITIES": "switch.plug"}}).status_code == 200
        assert settings.ha_house_write_entities == "switch.plug"
        assert client.post("/api/house/actions", headers=auth, json={"entity_id": "light.lamp", "action": "turn_on"}).status_code == 422
        assert client.put("/api/admin/settings", headers=auth, json={"values": {"HA_HOUSE_WRITE_ENTITIES": ""}}).status_code == 200
        assert client.get("/api/house/controls", headers=auth).json()["status"] == "not_configured"
        assert not [c for c in controls.calls if c.request.url.host == "ha.test"]
    finally:
        row = session.get(ConfigOverride, "HA_HOUSE_WRITE_ENTITIES")
        if row:
            session.delete(row)
            session.commit()


@pytest.mark.parametrize("mode", ["disabled", "removed", "no_url", "no_token"])
def test_house_revocation_after_metadata_blocks_direct_endpoints(client, auth, controls, monkeypatch, mode):
    state = controls.get("http://ha.test/api/states/light.lamp").respond(200, json={
        "entity_id": "light.lamp", "state": "on", "attributes": {},
    })
    assert client.get("/api/house/controls", headers=auth).json()["items"][0]["actions"]
    if mode == "disabled":
        monkeypatch.setattr(settings, "plugins_disabled", "homeassistant")
    elif mode == "removed":
        monkeypatch.setattr(settings, "ha_house_write_entities", "")
    else:
        monkeypatch.setattr(settings, "homeassistant_" + ("url" if mode == "no_url" else "token"), None)
    assert client.get("/api/house/controls", headers=auth).json()["status"] == "not_configured"
    assert client.post("/api/house/actions", headers=auth, json={"entity_id": "light.lamp", "action": "turn_off"}).status_code in (409, 422)
    assert state.call_count == 1


@pytest.mark.parametrize("mode", ["disabled", "removed", "changed_credentials"])
def test_house_revocation_during_state_check_never_posts(client, auth, controls, monkeypatch, mode):
    import httpx
    def state_response(request):
        if mode == "disabled":
            monkeypatch.setattr(settings, "plugins_disabled", "homeassistant")
        elif mode == "removed":
            monkeypatch.setattr(settings, "ha_house_write_entities", "")
        else:
            monkeypatch.setattr(settings, "homeassistant_token", "changed")
        return httpx.Response(200, json={"entity_id": "light.lamp", "state": "on"})
    controls.get("http://ha.test/api/states/light.lamp").mock(side_effect=state_response)
    response = client.post("/api/house/actions", headers=auth, json={"entity_id": "light.lamp", "action": "turn_off"})
    assert response.status_code in (409, 422)
    assert not [c for c in controls.calls if c.request.method == "POST" and c.request.url.host == "ha.test"]


@pytest.mark.parametrize("mode", ["timeout", "malformed", "missing"])
def test_house_controls_failure_and_state_check_failure_disable_actions(client, auth, controls, mode):
    import httpx
    route = controls.get("http://ha.test/api/states/light.lamp")
    if mode == "timeout":
        route.mock(side_effect=httpx.ReadTimeout("private"))
    elif mode == "malformed":
        route.respond(200, json={"entity_id": "light.lamp", "state": "on", "attributes": ["secret"]})
    else:
        route.respond(404, json={})
    response = client.get("/api/house/controls", headers=auth)
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable" and response.json()["error"]
    assert response.json()["items"][0]["actions"] == []
    assert "private" not in response.text and "secret" not in response.text
    assert client.post("/api/house/actions", headers=auth, json={"entity_id": "light.lamp", "action": "turn_on"}).status_code == 409


@pytest.mark.parametrize("brightness", [0, 255])
def test_house_brightness_inclusive_bounds(client, auth, controls, brightness):
    controls.get("http://ha.test/api/states/light.lamp").respond(200, json={
        "entity_id": "light.lamp", "state": "on", "attributes": {"supported_color_modes": ["brightness"]},
    })
    post = controls.post("http://ha.test/api/services/light/turn_on").respond(200, json=[])
    assert client.post("/api/house/actions", headers=auth, json={"entity_id": "light.lamp", "action": "brightness", "brightness": brightness}).status_code == 200
    assert json.loads(post.calls.last.request.content) == {"entity_id": "light.lamp", "brightness": brightness}


@pytest.mark.parametrize("entity,action", [("script.evening", "turn_off"), ("scene.evening", "turn_on"), ("switch.plug", "activate")])
def test_house_action_must_match_entity_kind(client, auth, controls, monkeypatch, entity, action):
    monkeypatch.setattr(settings, "ha_house_write_entities", entity)
    assert client.post("/api/house/actions", headers=auth, json={"entity_id": entity, "action": action}).status_code == 422
    assert not [c for c in controls.calls if c.request.url.host == "ha.test"]


@pytest.mark.parametrize("role", ["child", "guest"])
def test_house_canonical_readonly_roles_cannot_post(client, auth, controls, session, role):
    from app.core.security import create_access_token
    from app.models.user import ROLE_CHILD, ROLE_GUEST, User

    assert {ROLE_CHILD, ROLE_GUEST} == {"child", "guest"}
    user = User(username="house_canonical_" + role, email=role + "@canonical.test",
                role=role, is_admin=False, hashed_password="unused")
    session.add(user)
    session.commit()
    headers = {"Authorization": "Bearer " + create_access_token({"sub": user.username})}
    state = controls.get("http://ha.test/api/states/light.lamp").respond(200, json={
        "entity_id": "light.lamp", "state": "on",
        "attributes": {"brightness": 128, "supported_color_modes": ["brightness"]},
    })
    try:
        metadata = client.get("/api/house/controls", headers=headers)
        assert metadata.status_code == 200
        assert metadata.json()["items"][0]["actions"] == []
        assert client.post("/api/house/actions", headers=headers,
                           json={"entity_id": "light.lamp", "action": "turn_off"}).status_code == 403
        assert state.call_count == 1
        assert not [c for c in controls.calls if c.request.method == "POST" and c.request.url.host == "ha.test"]
    finally:
        session.delete(user)
        session.commit()


def test_house_action_returns_confirmed_state_from_ha(client, auth, controls):
    controls.get("http://ha.test/api/states/light.lamp").respond(200, json={
        "entity_id": "light.lamp", "state": "off", "attributes": {"supported_color_modes": ["brightness"]},
    })
    service = controls.post("http://ha.test/api/services/light/turn_on").respond(200, json=[
        {"entity_id": "light.other", "state": "on", "attributes": {}},
        {"entity_id": "light.lamp", "state": "on", "attributes": {
            "friendly_name": "Lampe", "brightness": 200, "supported_color_modes": ["brightness"], "private": "geheim"}},
    ])
    response = client.post("/api/house/actions", headers=auth,
                           json={"entity_id": "light.lamp", "action": "turn_on"})
    assert response.status_code == 200
    control = response.json()["control"]
    assert control["entity_id"] == "light.lamp" and control["state"] == "on" and control["brightness"] == 200
    assert "turn_off" in control["actions"]
    assert "geheim" not in response.text and "light.other" not in response.text
    assert service.call_count == 1  # genau einmal, keine Wiederholung


@pytest.mark.parametrize("payload", ["kein json", {"entity_id": "light.lamp"}, [{"entity_id": "light.lamp", "state": "unavailable"}]])
def test_house_action_ignores_unusable_ha_reply(client, auth, controls, payload):
    controls.get("http://ha.test/api/states/light.lamp").respond(200, json={
        "entity_id": "light.lamp", "state": "off", "attributes": {},
    })
    post = controls.post("http://ha.test/api/services/light/turn_on")
    if isinstance(payload, str):
        post.respond(200, text=payload)
    else:
        post.respond(200, json=payload)
    response = client.post("/api/house/actions", headers=auth,
                           json={"entity_id": "light.lamp", "action": "turn_on"})
    assert response.status_code == 200 and response.json() == {"accepted": True, "control": None}
