"""Persönlicher, extern bestätigter Zugang; kein vom Nutzer behaupteter Cutover."""
import respx
from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.core.crypto import decrypt
from app.models.habitica import HabiticaAccount
from tests.test_household import _household_user


def test_account_is_personal_encrypted_and_operator_cutover_is_separate(client, monkeypatch):
    user = _household_user("habitica-account")
    headers = {"Authorization": f"Bearer {create_access_token({'sub': user.username})}"}
    monkeypatch.setenv("HABITICA_URL", "https://habitica.example")
    payload = {"remote_user_id": "33333333-3333-4333-8333-333333333333", "api_key": "test-only-key"}
    with respx.mock(using="httpx") as http:
        http.route(host="testserver").pass_through()
        remote = http.get("https://habitica.example/api/v3/user").respond(200, json={"success": True, "data": {"id": payload["remote_user_id"]}})
        response = client.put("/api/habitica/account", headers=headers, json=payload)
        assert response.status_code == 200, response.text
        assert response.json()["writes_enabled"] is False
        assert remote.calls[0].request.headers["x-api-key"] == payload["api_key"]
        assert client.put("/api/habitica/account", headers=headers, json={**payload, "handoff_confirmed": True}).status_code == 422
    assert "test-only-key" not in client.get("/api/habitica/account", headers=headers).text
    with SessionLocal() as db:
        account = db.get(HabiticaAccount, user.id)
        assert account.api_key_enc != payload["api_key"]
        assert decrypt(account.api_key_enc) == payload["api_key"]
    other = _household_user("habitica-no-account")
    other_headers = {"Authorization": f"Bearer {create_access_token({'sub': other.username})}"}
    assert client.get("/api/habitica/account", headers=other_headers).json()["configured"] is False
    assert client.get("/api/habitica/tasks", headers=other_headers).json()["status"] == "not_configured"
