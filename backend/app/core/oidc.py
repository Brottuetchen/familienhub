"""OIDC-Hilfsfunktionen für Authorization Code + PKCE Flow."""

from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Dict, Optional

import httpx
from jose import jwt
from jose.exceptions import JWTError

from app.config import settings


def generate_pkce() -> Dict[str, str]:
    """Erzeuge PKCE code_verifier und code_challenge."""
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode('utf-8')).digest()
    ).decode('utf-8').rstrip('=')
    return {
        "code_verifier": code_verifier,
        "code_challenge": code_challenge,
    }


def generate_state() -> str:
    """Erzeuge einen zufälligen state-Parameter."""
    return secrets.token_urlsafe(32)


def generate_nonce() -> str:
    """Erzeuge einen zufälligen nonce-Parameter."""
    return secrets.token_urlsafe(32)


async def fetch_oidc_config() -> Dict:
    """Lade OpenID Configuration vom Issuer."""
    if not settings.oidc_issuer:
        raise ValueError("OIDC_ISSUER not configured")

    # Authentik-Issuer enden mit "/"; ohne rstrip entstünde "…//.well-known" (404)
    url = f"{settings.oidc_issuer.rstrip('/')}/.well-known/openid-configuration"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=10.0)
        response.raise_for_status()
        return response.json()


async def fetch_jwks(jwks_uri: str) -> Dict:
    """Lade JWKS (JSON Web Key Set) vom Provider."""
    async with httpx.AsyncClient() as client:
        response = await client.get(jwks_uri, timeout=10.0)
        response.raise_for_status()
        return response.json()


def verify_id_token(
    id_token: str,
    jwks: Dict,
    expected_nonce: str,
    expected_issuer: str,
    expected_audience: str,
) -> Optional[Dict]:
    """Verifiziere ID-Token: Signatur, Issuer, Audience, Expiry, Nonce."""

    # Dekodiere Header um kid zu finden
    try:
        unverified_header = jwt.get_unverified_header(id_token)
        kid = unverified_header.get("kid")
    except JWTError:
        return None

    # Finde passenden Key in JWKS
    key = None
    for jwk in jwks.get("keys", []):
        if jwk.get("kid") == kid:
            key = jwk
            break

    if not key:
        return None

    # Verifiziere Token mit dem öffentlichen Schlüssel
    try:
        # jwt.decode prüft automatisch exp, iss und aud
        payload = jwt.decode(
            id_token,
            key,
            algorithms=["RS256"],
            audience=expected_audience,
            issuer=expected_issuer,
        )
    except JWTError as e:
        # ponytail: log masked exception for debugging
        import logging
        logging.getLogger("familienhub").debug(f"ID token verification failed: {e}")
        return None

    # Prüfe nonce
    if payload.get("nonce") != expected_nonce:
        return None

    return payload


async def exchange_code_for_tokens(
    code: str,
    code_verifier: str,
    token_endpoint: str,
    redirect_uri: str,
) -> Dict:
    """Tausche Authorization Code gegen ID-Token und Access-Token."""
    if not settings.oidc_client_id or not settings.oidc_client_secret:
        raise ValueError("OIDC client credentials not configured")

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": settings.oidc_client_id,
        "client_secret": settings.oidc_client_secret,
        "code_verifier": code_verifier,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(token_endpoint, data=data, timeout=10.0)
        response.raise_for_status()
        return response.json()
