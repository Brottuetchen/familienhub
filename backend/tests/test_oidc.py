"""Tests für OIDC-Authentifizierung (WP 5)."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt

from app.core.database import SessionLocal
from app.models.user import User


# === Fixtures ===

@pytest.fixture
def rsa_keypair():
    """Erzeuge ein RSA-Schlüsselpaar für JWKS-Mock."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    # Private Key im PEM-Format
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')

    # Public Key Numbers für JWKS
    public_numbers = public_key.public_numbers()

    return {
        "private_key": private_key,
        "private_pem": private_pem,
        "public_numbers": public_numbers,
        "kid": "test-key-1"
    }


@pytest.fixture
def mock_oidc_config(rsa_keypair):
    """Mock OpenID Configuration und JWKS."""
    config = {
        "issuer": "https://auth.example.com",
        "authorization_endpoint": "https://auth.example.com/authorize",
        "token_endpoint": "https://auth.example.com/token",
        "jwks_uri": "https://auth.example.com/.well-known/jwks.json",
    }

    # JWKS mit öffentlichem Schlüssel
    n = rsa_keypair["public_numbers"].n
    e = rsa_keypair["public_numbers"].e

    # Convert to base64url
    n_bytes = n.to_bytes((n.bit_length() + 7) // 8, byteorder='big')
    e_bytes = e.to_bytes((e.bit_length() + 7) // 8, byteorder='big')
    n_b64 = base64.urlsafe_b64encode(n_bytes).decode('utf-8').rstrip('=')
    e_b64 = base64.urlsafe_b64encode(e_bytes).decode('utf-8').rstrip('=')

    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "kid": rsa_keypair["kid"],
                "use": "sig",
                "alg": "RS256",
                "n": n_b64,
                "e": e_b64,
            }
        ]
    }

    return {"config": config, "jwks": jwks}


@pytest.fixture
def test_user():
    """Erstelle einen Testnutzer mit E-Mail."""
    db = SessionLocal()
    try:
        # Lösche ggf. bestehenden Testnutzer
        existing = db.query(User).filter(User.username == "oidc_testuser").first()
        if existing:
            db.delete(existing)
            db.commit()

        user = User(
            username="oidc_testuser",
            email="oidc_test@example.com",
            hashed_password="dummy",
            role="partner",
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


# === Tests ===

def test_oidc_start_contains_pkce_and_state(client):
    """OIDC-Start erzeugt URL mit state, nonce und code_challenge."""
    with patch("app.config.settings.oidc_issuer", "https://auth.example.com"):
        with patch("app.config.settings.oidc_client_id", "test-client"):
            with patch("app.config.settings.oidc_redirect_uri_web", "http://localhost:8000/api/auth/oidc/callback"):
                with patch("app.routers.auth.fetch_oidc_config") as mock_fetch:
                    mock_fetch.return_value = {
                        "issuer": "https://auth.example.com",
                        "authorization_endpoint": "https://auth.example.com/authorize",
                        "token_endpoint": "https://auth.example.com/token",
                        "jwks_uri": "https://auth.example.com/.well-known/jwks.json",
                    }
                    response = client.get("/api/auth/oidc/start?client=web")

    assert response.status_code == 200
    data = response.json()
    assert "url" in data
    url = data["url"]

    # Prüfe, dass die URL die richtigen Parameter enthält
    assert "state=" in url
    assert "nonce=" in url
    assert "code_challenge=" in url
    assert "code_challenge_method=S256" in url
    assert "response_type=code" in url
    assert "client_id=test-client" in url


def test_callback_rejects_wrong_state(client, mock_oidc_config, rsa_keypair, test_user):
    """Callback lehnt ID-Token mit falschem state ab."""
    with patch("app.config.settings.oidc_issuer", mock_oidc_config["config"]["issuer"]):
        with patch("app.config.settings.oidc_client_id", "test-client"):
            with patch("app.config.settings.oidc_redirect_uri_web", "http://localhost:8000/api/auth/oidc/callback"):
                with patch("app.routers.auth.fetch_oidc_config") as mock_fetch_config:
                    mock_fetch_config.return_value = mock_oidc_config["config"]

                    # Starte OIDC-Flow um state zu erzeugen
                    start_response = client.get("/api/auth/oidc/start?client=web")
                    assert start_response.status_code == 200

                    # Versuche Callback mit falschem state
                    callback_response = client.get("/api/auth/oidc/callback?code=dummy&state=wrong_state")
                    assert callback_response.status_code in (400, 401, 403)


def test_callback_rejects_bad_signature(client, mock_oidc_config, test_user):
    """Callback lehnt ID-Token mit ungültiger Signatur ab."""

    # Erzeuge einen falschen Schlüssel
    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    wrong_pem = wrong_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')

    with patch("app.config.settings.oidc_issuer", mock_oidc_config["config"]["issuer"]):
        with patch("app.config.settings.oidc_client_id", "test-client"):
            with patch("app.config.settings.oidc_redirect_uri_web", "http://localhost:8000/api/auth/oidc/callback"):
                with patch("app.routers.auth.fetch_oidc_config") as mock_fetch_config:
                    with patch("app.routers.auth.fetch_jwks") as mock_fetch_jwks:
                        with patch("app.routers.auth.exchange_code_for_tokens") as mock_exchange:
                            mock_fetch_config.return_value = mock_oidc_config["config"]
                            mock_fetch_jwks.return_value = mock_oidc_config["jwks"]

                            # Starte Flow
                            start_response = client.get("/api/auth/oidc/start?client=web")
                            assert start_response.status_code == 200

                            # Extrahiere state aus der URL
                            data = start_response.json()
                            url = data["url"]
                            state = url.split("state=")[1].split("&")[0]

                            # Hole nonce aus der DB
                            from app.core.database import SessionLocal
                            from app.models.oidc import OIDCSession
                            db = SessionLocal()
                            oidc_session = db.query(OIDCSession).filter(OIDCSession.state == state).first()
                            nonce = oidc_session.nonce if oidc_session else "test_nonce"
                            db.close()

                            # Erstelle ID-Token mit falschem Schlüssel
                            id_token_payload = {
                                "iss": mock_oidc_config["config"]["issuer"],
                                "aud": "test-client",
                                "sub": "user123",
                                "email": test_user.email,
                                "nonce": nonce,
                                "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
                                "iat": int(datetime.utcnow().timestamp()),
                            }

                            id_token = jwt.encode(id_token_payload, wrong_pem, algorithm="RS256", headers={"kid": "wrong-key"})

                            mock_exchange.return_value = {
                                "id_token": id_token,
                                "access_token": "dummy_access"
                            }

                            # Callback sollte fehlschlagen wegen falscher Signatur
                            callback_response = client.get(f"/api/auth/oidc/callback?code=authcode&state={state}")
                            assert callback_response.status_code in (401, 403)


def test_callback_maps_email_case_insensitive(client, mock_oidc_config, rsa_keypair, test_user):
    """Callback ordnet E-Mail case-insensitive zu."""

    with patch("app.config.settings.oidc_issuer", mock_oidc_config["config"]["issuer"]):
        with patch("app.config.settings.oidc_client_id", "test-client"):
            with patch("app.config.settings.oidc_redirect_uri_web", "http://localhost:8000/api/auth/oidc/callback"):
                with patch("app.routers.auth.fetch_oidc_config") as mock_fetch_config:
                    with patch("app.routers.auth.fetch_jwks") as mock_fetch_jwks:
                        with patch("app.routers.auth.exchange_code_for_tokens") as mock_exchange:
                            with patch("app.routers.auth.verify_id_token") as mock_verify:
                                mock_fetch_config.return_value = mock_oidc_config["config"]
                                mock_fetch_jwks.return_value = mock_oidc_config["jwks"]
                                mock_verify.return_value = {
                                    "iss": mock_oidc_config["config"]["issuer"],
                                    "aud": "test-client",
                                    "sub": "user123",
                                    "email": test_user.email.upper(),
                                }

                                # Starte Flow und hole state/nonce aus Session
                                start_response = client.get("/api/auth/oidc/start?client=web")
                                assert start_response.status_code == 200

                                # Extrahiere state
                                data = start_response.json()
                                url = data["url"]
                                state = url.split("state=")[1].split("&")[0]

                                mock_exchange.return_value = {
                                    "id_token": "dummy_token",
                                    "access_token": "dummy_access"
                                }

                                # Simuliere erfolgreichen Callback
                                callback_response = client.get(
                                    f"/api/auth/oidc/callback?code=authcode&state={state}", follow_redirects=False
                                )

                                # Erfolgreich: Weiterleitung auf die Startseite (nicht 403)
                                assert callback_response.status_code == 302


def test_unknown_email_403(client, mock_oidc_config, rsa_keypair):
    """Callback gibt 403 bei unbekannter E-Mail ohne AUTO_CREATE."""

    with patch("app.config.settings.oidc_issuer", mock_oidc_config["config"]["issuer"]):
        with patch("app.config.settings.oidc_client_id", "test-client"):
            with patch("app.config.settings.oidc_redirect_uri_web", "http://localhost:8000/api/auth/oidc/callback"):
                with patch("app.config.settings.oidc_auto_create", False):
                    with patch("app.routers.auth.fetch_oidc_config") as mock_fetch_config:
                        with patch("app.routers.auth.fetch_jwks") as mock_fetch_jwks:
                            with patch("app.routers.auth.exchange_code_for_tokens") as mock_exchange:
                                with patch("app.routers.auth.verify_id_token") as mock_verify:
                                        mock_fetch_config.return_value = mock_oidc_config["config"]
                                        mock_fetch_jwks.return_value = mock_oidc_config["jwks"]
                                        mock_verify.return_value = {
                                            "iss": mock_oidc_config["config"]["issuer"],
                                            "aud": "test-client",
                                            "sub": "unknown_user",
                                            "email": "unknown@example.com",
                                        }

                                        # Starte Flow
                                        start_response = client.get("/api/auth/oidc/start?client=web")
                                        assert start_response.status_code == 200

                                        # Extrahiere state und nonce
                                        data = start_response.json()
                                        url = data["url"]
                                        state = url.split("state=")[1].split("&")[0]

                                        from app.core.database import SessionLocal
                                        from app.models.oidc import OIDCSession
                                        db = SessionLocal()
                                        oidc_session = db.query(OIDCSession).filter(OIDCSession.state == state).first()
                                        nonce = oidc_session.nonce
                                        db.close()

                                        # Erstelle ID-Token mit unbekannter E-Mail
                                        id_token_payload = {
                                            "iss": mock_oidc_config["config"]["issuer"],
                                            "aud": "test-client",
                                            "sub": "unknown_user",
                                            "email": "unknown@example.com",
                                            "nonce": nonce,
                                            "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
                                            "iat": int(datetime.utcnow().timestamp()),
                                        }

                                        id_token = jwt.encode(
                                            id_token_payload,
                                            rsa_keypair["private_pem"],
                                            algorithm="RS256",
                                            headers={"kid": rsa_keypair["kid"]}
                                        )

                                        mock_exchange.return_value = {
                                            "id_token": id_token,
                                            "access_token": "dummy_access"
                                        }

                                        callback_response = client.get(f"/api/auth/oidc/callback?code=authcode&state={state}")
                                        assert callback_response.status_code == 403


def test_app_exchange_code_single_use_and_expires(client, mock_oidc_config, rsa_keypair, test_user):
    """App-Exchange-Code ist einmalig verwendbar und läuft ab."""

    with patch("app.config.settings.oidc_issuer", mock_oidc_config["config"]["issuer"]):
        with patch("app.config.settings.oidc_client_id", "test-client"):
            with patch("app.config.settings.oidc_redirect_uri_app", "familienhub://auth"):
                with patch("app.routers.auth.fetch_oidc_config") as mock_fetch_config:
                    with patch("app.routers.auth.fetch_jwks") as mock_fetch_jwks:
                        with patch("app.routers.auth.exchange_code_for_tokens") as mock_exchange:
                            with patch("app.routers.auth.verify_id_token") as mock_verify:
                                mock_fetch_config.return_value = mock_oidc_config["config"]
                                mock_fetch_jwks.return_value = mock_oidc_config["jwks"]
                                mock_verify.return_value = {
                                    "iss": mock_oidc_config["config"]["issuer"],
                                    "aud": "test-client",
                                    "sub": "user123",
                                    "email": test_user.email,
                                }

                                # Starte App-Flow
                                start_response = client.get("/api/auth/oidc/start?client=app")
                                assert start_response.status_code == 200

                                # Extrahiere state
                                data = start_response.json()
                                url = data["url"]
                                state = url.split("state=")[1].split("&")[0]

                                # Hole nonce aus der DB
                                from app.core.database import SessionLocal
                                from app.models.oidc import OIDCSession
                                db = SessionLocal()
                                oidc_session = db.query(OIDCSession).filter(OIDCSession.state == state).first()
                                nonce = oidc_session.nonce
                                db.close()

                                # Erstelle ID-Token
                                id_token_payload = {
                                    "iss": mock_oidc_config["config"]["issuer"],
                                    "aud": "test-client",
                                    "sub": "user123",
                                    "email": test_user.email,
                                    "nonce": nonce,
                                    "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
                                    "iat": int(datetime.utcnow().timestamp()),
                                }

                                id_token = jwt.encode(
                                    id_token_payload,
                                    rsa_keypair["private_pem"],
                                    algorithm="RS256",
                                    headers={"kid": rsa_keypair["kid"]}
                                )

                                mock_exchange.return_value = {
                                    "id_token": id_token,
                                    "access_token": "dummy_access"
                                }

                                # Simuliere Callback für App (gibt Exchange-Code zurück)
                                callback_response = client.get(f"/api/auth/oidc/callback?code=authcode&state={state}", follow_redirects=False)

                                # Sollte Redirect zu familienhub://auth?code=... enthalten
                                assert callback_response.status_code in (302, 307)
                                location = callback_response.headers.get("location", "")
                                assert "familienhub://auth?code=" in location

                                # Extrahiere Exchange-Code
                                exchange_code = location.split("code=")[1].split("&")[0] if "code=" in location else None
                                assert exchange_code is not None

                                # Erster Austausch sollte funktionieren
                                exchange_response = client.post(
                                    "/api/auth/oidc/exchange",
                                    json={"code": exchange_code}
                                )
                                assert exchange_response.status_code == 200
                                assert "access_token" in exchange_response.json()
                                # Die App hat keine Cookies: Refresh-Token kommt im Body
                                assert exchange_response.json()["refresh_token"]

                                # Zweiter Austausch mit demselben Code sollte fehlschlagen
                                exchange_response2 = client.post(
                                    "/api/auth/oidc/exchange",
                                    json={"code": exchange_code}
                                )
                                assert exchange_response2.status_code in (400, 401)





def test_app_exchange_code_expires_after_60_seconds(client, test_user):
    """Ein Austauschcode, der älter als 60 s ist, wird mit 401 abgelehnt und gelöscht (Ergänzung zu WP 5)."""
    from datetime import datetime, timedelta

    from app.core.database import SessionLocal
    from app.models.oidc import OIDCExchangeCode

    with SessionLocal() as db:
        db.add(OIDCExchangeCode(code="abgelaufen-123", user_id=test_user.id, used=False,
                                created_at=datetime.utcnow() - timedelta(seconds=61)))
        db.commit()

    response = client.post("/api/auth/oidc/exchange", json={"code": "abgelaufen-123"})
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()

    with SessionLocal() as db:
        assert db.query(OIDCExchangeCode).filter_by(code="abgelaufen-123").first() is None


def test_discovery_url_without_double_slash(monkeypatch):
    """Issuer mit abschließendem / (Authentik) → genau ein / vor .well-known."""
    import asyncio

    import httpx

    from app.config import settings
    from app.core import oidc

    seen = []

    async def fake_get(self, url, **kwargs):
        seen.append(url)
        return httpx.Response(200, json={"issuer": "x"}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    for issuer in ("https://idp.example.test/application/o/hub/", "https://idp.example.test/application/o/hub"):
        monkeypatch.setattr(settings, "oidc_issuer", issuer)
        asyncio.run(oidc.fetch_oidc_config())
    assert seen == ["https://idp.example.test/application/o/hub/.well-known/openid-configuration"] * 2


def _run_callback(client, mock_oidc_config, rsa_keypair, client_type, email):
    """Start + Callback mit gefälschtem Authentik; liefert die Callback-Antwort ohne Redirect-Folgen."""
    from app.models.oidc import OIDCSession

    issuer = mock_oidc_config["config"]["issuer"]
    with patch("app.config.settings.oidc_issuer", issuer), \
            patch("app.config.settings.oidc_client_id", "test-client"), \
            patch("app.config.settings.oidc_redirect_uri_web", "https://hub.example.test/api/auth/oidc/callback"), \
            patch("app.config.settings.oidc_redirect_uri_app", "https://hub.example.test/api/auth/oidc/callback"), \
            patch("app.routers.auth.fetch_oidc_config", return_value=mock_oidc_config["config"]), \
            patch("app.routers.auth.fetch_jwks", return_value=mock_oidc_config["jwks"]), \
            patch("app.routers.auth.exchange_code_for_tokens") as mock_exchange, \
            patch("app.routers.auth.verify_id_token") as mock_verify:
        url = client.get(f"/api/auth/oidc/start?client={client_type}").json()["url"]
        state = url.split("state=")[1].split("&")[0]
        with SessionLocal() as db:
            nonce = db.query(OIDCSession).filter(OIDCSession.state == state).first().nonce
        id_token = jwt.encode(
            {"iss": issuer, "aud": "test-client", "sub": "u1", "email": email, "nonce": nonce,
             "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
             "iat": int(datetime.utcnow().timestamp())},
            rsa_keypair["private_pem"], algorithm="RS256", headers={"kid": rsa_keypair["kid"]},
        )
        mock_exchange.return_value = {"id_token": id_token, "access_token": "x"}
        mock_verify.return_value = {"iss": issuer, "aud": "test-client", "sub": "u1", "email": email}
        return client.get(f"/api/auth/oidc/callback?code=authcode&state={state}", follow_redirects=False)


def test_web_callback_sets_auth_cookies(client, mock_oidc_config, rsa_keypair, test_user):
    """Web-Login: Cookies müssen auf der Redirect-Antwort landen (gingen vorher verloren)."""
    resp = _run_callback(client, mock_oidc_config, rsa_keypair, "web", test_user.email)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/"
    cookies = resp.headers.get_list("set-cookie")
    assert any(c.startswith("access_token=") for c in cookies)
    assert any(c.startswith("refresh_token=") for c in cookies)


def test_app_callback_unknown_user_returns_to_app(client, mock_oidc_config, rsa_keypair):
    resp = _run_callback(client, mock_oidc_config, rsa_keypair, "app", "niemand@example.test")
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "familienhub://auth?error=unknown_user"


def test_app_callback_provider_error_returns_to_app(client, mock_oidc_config):
    """Authentik schickt ?error=… ohne code → zurück in die App statt 422 im Browser."""
    with patch("app.config.settings.oidc_issuer", mock_oidc_config["config"]["issuer"]), \
            patch("app.config.settings.oidc_client_id", "test-client"), \
            patch("app.config.settings.oidc_redirect_uri_app", "https://hub.example.test/api/auth/oidc/callback"), \
            patch("app.routers.auth.fetch_oidc_config", return_value=mock_oidc_config["config"]):
        url = client.get("/api/auth/oidc/start?client=app").json()["url"]
        state = url.split("state=")[1].split("&")[0]
        resp = client.get(f"/api/auth/oidc/callback?error=access_denied&state={state}", follow_redirects=False)
    assert resp.headers["location"] == "familienhub://auth?error=cancelled"


def test_web_callback_without_code_400(client):
    assert client.get("/api/auth/oidc/callback?state=x").status_code == 400


def test_pwa_callback_redirects_to_page_with_code(client, mock_oidc_config, rsa_keypair, test_user):
    """Web-App: Rücksprung auf /?oidc_code=…, Code ist per /oidc/exchange einlösbar."""
    resp = _run_callback(client, mock_oidc_config, rsa_keypair, "pwa", test_user.email)
    assert resp.status_code == 302
    loc = resp.headers["location"]
    assert loc.startswith("/?oidc_code=")
    code = loc.split("oidc_code=")[1]
    ex = client.post("/api/auth/oidc/exchange", json={"code": code})
    assert ex.status_code == 200
    assert ex.json()["refresh_token"]


def test_pwa_callback_unknown_user_redirects_with_error(client, mock_oidc_config, rsa_keypair):
    resp = _run_callback(client, mock_oidc_config, rsa_keypair, "pwa", "niemand@example.test")
    assert resp.status_code == 302
    assert resp.headers["location"] == "/?oidc_error=unknown_user"


def test_oidc_start_rejects_unknown_client(client):
    with patch("app.config.settings.oidc_issuer", "https://auth.example.com"), \
            patch("app.config.settings.oidc_client_id", "test-client"):
        assert client.get("/api/auth/oidc/start?client=desktop").status_code == 400
