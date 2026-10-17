"""Haus-Karte (#28): echte Heute-API, Home Assistant nur als HTTP-Fake."""

import asyncio

import httpx
import pytest
import respx

from app.config import settings


@pytest.fixture
def house_ha(monkeypatch):
    monkeypatch.setattr(settings, "homeassistant_url", "http://ha.test")
    monkeypatch.setattr(settings, "homeassistant_token", "test-token")
    monkeypatch.setattr(settings, "ha_house_entities", "sensor.room_temperature,binary_sensor.baby_monitor")


@pytest.fixture
def house_http():
    # HTTPX-Transport: Methoden bleiben mit den gepinnten httpx/respx-Versionen Strings.
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        http.post("http://ha.test/api/services/todo/get_items").respond(200, json={})
        http.get("http://ha.test/api/calendars/calendar.cookidoo_speiseplan").respond(200, json=[])
        yield http


def test_today_house_timeout_overlaps_existing_ha_requests(client, auth, house_ha, house_http):
    in_flight = set()
    house_overlapped = False

    async def delayed_timeout(request):
        nonlocal house_overlapped
        path = request.url.path
        in_flight.add(path)
        try:
            # Jeder HA-Aufruf bleibt bis zum nächsten Eventloop-Durchlauf offen.
            await asyncio.sleep(0)
            if "/api/states" in in_flight and len(in_flight) > 1:
                house_overlapped = True
            raise httpx.ReadTimeout("HA timed out", request=request)
        finally:
            in_flight.remove(path)

    calendar = house_http.get("http://ha.test/api/calendars/calendar.cookidoo_speiseplan").mock(
        side_effect=delayed_timeout,
    )
    shopping = house_http.post("http://ha.test/api/services/todo/get_items").mock(side_effect=delayed_timeout)
    states = house_http.get("http://ha.test/api/states").mock(side_effect=delayed_timeout)

    response = client.get("/api/today", headers=auth)

    assert response.status_code == 200
    data = response.json()
    assert data["house"]["status"] == "unavailable"
    assert data["house"]["error"] and data["house"]["items"] == []
    assert "meals" in data and "tasks" in data and data["shopping_open"] == 0
    assert calendar.call_count == shopping.call_count == states.call_count == 1
    # Kein dritter serieller HA-Timeout zusätzlich zu Kalender und Einkauf.
    assert house_overlapped, "House timeout must overlap existing HA requests, not extend the Today budget"


def test_today_house_only_selected_states_in_configured_order(client, auth, house_ha, house_http):
    states = house_http.get("http://ha.test/api/states").respond(200, json=[
        {"entity_id": "sensor.private", "state": "secret", "attributes": {"friendly_name": "Privat"}},
        {"entity_id": "binary_sensor.baby_monitor", "state": "on", "attributes": {"friendly_name": "Babyphon"}},
        {"entity_id": "sensor.room_temperature", "state": "21.5", "attributes": {
            "friendly_name": "Kinderzimmer", "unit_of_measurement": "°C", "private": "secret",
        }},
    ])
    response = client.get("/api/today", headers=auth)
    assert response.status_code == 200
    assert response.json()["house"] == {
        "status": "ok", "error": None, "items": [
            {"entity_id": "sensor.room_temperature", "name": "Kinderzimmer", "state": "21.5", "unit": "°C"},
            {"entity_id": "binary_sensor.baby_monitor", "name": "Babyphon", "state": "on", "unit": None},
        ],
    }
    assert states.call_count == 1
    assert states.calls.last.request.headers["Authorization"] == "Bearer test-token"


@pytest.mark.parametrize("mode", ["empty", "disabled", "no_url", "no_token"])
def test_today_house_not_configured_never_reads_states(client, auth, house_ha, house_http, monkeypatch, mode):
    if mode == "empty":
        monkeypatch.setattr(settings, "ha_house_entities", "")
    elif mode == "disabled":
        monkeypatch.setattr(settings, "plugins_disabled", "homeassistant")
    elif mode == "no_url":
        monkeypatch.setattr(settings, "homeassistant_url", None)
    else:
        monkeypatch.setattr(settings, "homeassistant_token", None)
    route = house_http.get("http://ha.test/api/states").respond(200, json=[])
    assert client.get("/api/today", headers=auth).json()["house"] == {
        "status": "not_configured", "error": None, "items": [],
    }
    assert not route.called


@pytest.mark.parametrize("status,payload", [(503, {}), (200, {}), (200, [None])])
def test_today_house_failure_keeps_other_cards(client, auth, house_ha, house_http, caplog, status, payload):
    house_http.get("http://ha.test/api/states").respond(status, json=payload)
    response = client.get("/api/today", headers=auth)
    assert response.status_code == 200
    data = response.json()
    assert data["house"]["status"] == "unavailable"
    assert data["house"]["error"]
    assert data["house"]["items"] == []
    assert "meals" in data and "tasks" in data
    assert any(r.name == "connector.homeassistant" and r.exc_info for r in caplog.records)


@pytest.mark.parametrize("state", [None, "unknown", "unavailable"])
def test_today_house_missing_or_unavailable_entity_preserves_others(client, auth, house_ha, house_http, state):
    states = [{"entity_id": "sensor.room_temperature", "state": "21.5", "attributes": {}}]
    if state is not None:
        states.append({"entity_id": "binary_sensor.baby_monitor", "state": state, "attributes": {}})
    house_http.get("http://ha.test/api/states").respond(200, json=states)
    house = client.get("/api/today", headers=auth).json()["house"]
    assert house["status"] == "unavailable" and house["error"]
    assert house["items"] == [
        {"entity_id": "sensor.room_temperature", "name": "sensor.room_temperature", "state": "21.5", "unit": None},
        {"entity_id": "binary_sensor.baby_monitor", "name": "binary_sensor.baby_monitor", "state": None, "unit": None},
    ]


@pytest.mark.parametrize("value", ["sensor.ok,../secret", ",".join(f"sensor.s{i}" for i in range(7))])
def test_today_house_invalid_config_does_not_read_states(client, auth, house_ha, house_http, monkeypatch, value):
    monkeypatch.setattr(settings, "ha_house_entities", value)
    route = house_http.get("http://ha.test/api/states").respond(200, json=[])
    house = client.get("/api/today", headers=auth).json()["house"]
    assert house["status"] == "unavailable" and house["error"]
    assert not route.called


@pytest.mark.parametrize("value", ["sensor.ok,/bad", ",".join(f"sensor.s{i}" for i in range(7))])
def test_house_admin_rejects_invalid_selection_atomically(client, auth, house_ha, session, value):
    from app.models.config import ConfigOverride

    before = settings.ha_house_entities
    response = client.put("/api/admin/settings", headers=auth,
                          json={"values": {"HA_HOUSE_ENTITIES": value}})
    try:
        assert response.status_code == 422
        assert settings.ha_house_entities == before
        assert session.get(ConfigOverride, "HA_HOUSE_ENTITIES") is None
    finally:
        row = session.get(ConfigOverride, "HA_HOUSE_ENTITIES")
        if row:
            session.delete(row)
            session.commit()


def test_house_admin_selection_applies_live_and_can_be_cleared(client, auth, house_ha, house_http, session):
    from app.models.config import ConfigOverride

    house_http.get("http://ha.test/api/states").respond(200, json=[
        {"entity_id": "sensor.washer", "state": "Fertig", "attributes": {}},
    ])
    try:
        response = client.put("/api/admin/settings", headers=auth,
                              json={"values": {"HA_HOUSE_ENTITIES": " sensor.washer, sensor.washer "}})
        assert response.status_code == 200
        data = client.get("/api/today", headers=auth).json()["house"]
        assert data["status"] == "ok" and len(data["items"]) == 1
        assert data["items"][0]["state"] == "Fertig"
        fields = next(p for p in client.get("/api/admin/settings", headers=auth).json()
                      if p["id"] == "homeassistant")["fields"]
        assert next(f for f in fields if f["key"] == "HA_HOUSE_ENTITIES")["value"] == "sensor.washer, sensor.washer"
        assert session.get(ConfigOverride, "HA_HOUSE_ENTITIES").value == "sensor.washer, sensor.washer"
        assert client.put("/api/admin/settings", headers=auth,
                          json={"values": {"HA_HOUSE_ENTITIES": ""}}).status_code == 200
        assert client.get("/api/today", headers=auth).json()["house"]["status"] == "not_configured"
    finally:
        row = session.get(ConfigOverride, "HA_HOUSE_ENTITIES")
        if row:
            session.delete(row)
            session.commit()
