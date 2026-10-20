"""Authentifizierungs- und Benutzerverwaltungs-Endpunkte."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, ConfigDict, model_validator
from sqlalchemy.orm import Session

from app.config import settings
from app.core.database import get_db
from app.core.ingress import cookie_path, resolve_prefix
from app.core.oidc import (
    exchange_code_for_tokens,
    fetch_jwks,
    fetch_oidc_config,
    generate_nonce,
    generate_pkce,
    generate_state,
    verify_id_token,
)
from app.core.security import (
    revoke_all_refresh_tokens,
    authenticate_user,
    check_rate_limit,
    clear_auth_cookies,
    create_access_token,
    create_refresh_token,
    get_current_admin_user,
    get_current_user,
    get_password_hash,
    log_login_attempt,
    revoke_refresh_token,
    set_auth_cookies,
    verify_password,
    verify_refresh_token,
)
from app.models.oidc import OIDCExchangeCode, OIDCSession
from app.models.user import VALID_ROLES, User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str
    # "app": Refresh-Token zusätzlich im Body (native App hat keine Cookies)
    client: str = "web"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None
    user: dict


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str] = None
    display_name: Optional[str] = None
    avatar_color: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str
    is_admin: bool
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def _profile(cls, value):
        # Anzeigename mit Rückfall (Anzeigename → voller Name → Benutzername), Profilbild-URL
        if isinstance(value, User):
            return {**{c.name: getattr(value, c.name) for c in value.__table__.columns},
                    "display_name": value.effective_name, "avatar_url": value.avatar_url}
        return value


class CreateUserRequest(BaseModel):
    username: str
    email: str
    password: str
    full_name: Optional[str] = None
    role: str = "partner"


class UpdateUserRequest(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=200)
    refresh_token: Optional[str] = None  # diese Sitzung behalten (App), alle anderen beenden


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, response: Response, data: LoginRequest, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(data.username, ip, db):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts.")

    user = authenticate_user(data.username, data.password, db)
    if not user:
        log_login_attempt(data.username, ip, success=False, db=db)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")

    log_login_attempt(data.username, ip, success=True, db=db)
    access = create_access_token(data={"sub": user.username})
    refresh = create_refresh_token(user.id, db, request)
    set_auth_cookies(response, access, refresh)
    return {
        "access_token": access,
        "token_type": "bearer",
        "refresh_token": refresh if data.client == "app" else None,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_admin": user.is_admin,
        },
    }


@router.post("/logout")
async def logout(request: Request, response: Response, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    token = request.cookies.get("refresh_token")
    if token:
        revoke_refresh_token(token, db)
    clear_auth_cookies(response)
    return {"message": "Successfully logged out"}


class RefreshRequest(BaseModel):
    refresh_token: Optional[str] = None


@router.post("/refresh")
async def refresh_token(
    request: Request,
    response: Response,
    data: Optional[RefreshRequest] = None,
    db: Session = Depends(get_db),
):
    """Neues Access-Token.

    Web: Refresh-Token aus dem Cookie. App: Refresh-Token im Body; dann wird es
    rotiert (altes widerrufen, neues zurückgegeben), damit die Anmeldung bei
    regelmäßiger Nutzung nicht nach 7 Tagen abläuft.
    """
    body_token = data.refresh_token if data else None
    token = body_token or request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token not found")
    db_token = verify_refresh_token(token, db)
    if not db_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")
    user = db.query(User).filter(User.id == db_token.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    access = create_access_token(data={"sub": user.username})
    if body_token:
        revoke_refresh_token(token, db)
        new_refresh = create_refresh_token(user.id, db, request)
        return {"access_token": access, "token_type": "bearer", "refresh_token": new_refresh}
    response.set_cookie(key="access_token", value=access, httponly=True, samesite="lax", path=cookie_path())
    return {"access_token": access, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/change-password")
async def change_password(data: ChangePasswordRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    current_user.hashed_password = get_password_hash(data.new_password)
    db.commit()
    # Andere Geräte abmelden: wer das alte Passwort kannte, soll nicht angemeldet bleiben
    ended = revoke_all_refresh_tokens(current_user.id, db, keep=data.refresh_token or request.cookies.get("refresh_token"))
    return {"message": "Password changed successfully", "other_sessions_ended": ended}


# --- User management (admin) ---

@router.get("/people")
async def list_people(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Aktive Nutzer für die Auswahl „Aufgabe für …“ (ohne E-Mail und Rollen)."""
    users = db.query(User).filter(User.is_active == True).order_by(User.id).all()  # noqa: E712
    return [
        {"id": u.id, "username": u.username, "display_name": u.effective_name,
         "avatar_color": u.avatar_color, "avatar_url": u.avatar_url}
        for u in users
    ]


@router.get("/users", response_model=list[UserResponse])
async def list_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    return db.query(User).all()


@router.post("/users", response_model=UserResponse)
async def create_user(data: CreateUserRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    if data.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Valid: {', '.join(sorted(VALID_ROLES))}")
    data.username = data.username.strip().lower()  # stored lowercase like setup and invites; sign-in compares exactly
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Username already registered")
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        username=data.username,
        email=data.email,
        hashed_password=get_password_hash(data.password),
        full_name=data.full_name,
        role=data.role,
        is_admin=(data.role == "admin"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, updates: UpdateUserRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id and updates.role and updates.role != "admin":
        raise HTTPException(status_code=400, detail="Eigene Admin-Rechte kann man nicht entfernen")
    if user.id == current_user.id and updates.is_active is False:
        raise HTTPException(status_code=400, detail="Sich selbst kann man nicht deaktivieren")
    if updates.email is not None:
        user.email = updates.email
    if updates.full_name is not None:
        user.full_name = updates.full_name
    if updates.role is not None:
        if updates.role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail="Invalid role")
        user.role = updates.role
        user.is_admin = updates.role == "admin"
    if updates.is_active is not None:
        user.is_active = updates.is_active
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"message": f"User {user.username} deleted"}


# --- OIDC (OpenID Connect) ---

class OIDCStartResponse(BaseModel):
    url: str


class OIDCExchangeRequest(BaseModel):
    code: str
    verifier: Optional[str] = Field(default=None, max_length=200)  # Geheimnis zum challenge aus /oidc/start


@router.get("/oidc/start", response_model=OIDCStartResponse)
async def oidc_start(client: str, challenge: Optional[str] = None, db: Session = Depends(get_db)):
    """Starte OIDC Authorization Code Flow mit PKCE."""
    if not settings.oidc_issuer or not settings.oidc_client_id:
        raise HTTPException(status_code=501, detail="OIDC not configured")

    # web: Cookies (alte Weboberfläche) · app: familienhub://-Rücksprung · pwa: Web-App, Rücksprung auf /?oidc_code=
    if client not in ("web", "app", "pwa"):
        raise HTTPException(status_code=400, detail="Invalid client type")
    challenge = _valid_challenge(challenge)  # vor jedem Netzaufruf prüfen

    # Hole OIDC-Konfiguration
    try:
        oidc_config = await fetch_oidc_config()
    except Exception:
        raise HTTPException(status_code=503, detail="OIDC provider unreachable")

    # Erzeuge PKCE, state und nonce
    pkce = generate_pkce()
    state = generate_state()
    nonce = generate_nonce()

    # Speichere Session
    oidc_session = OIDCSession(
        state=state,
        nonce=nonce,
        code_verifier=pkce["code_verifier"],
        client_type=client,
        # App/Web-App: Hash eines Geheimnisses, das nur das startende Gerät kennt (PKCE-Bindung des Rücksprungs)
        app_challenge=challenge,
    )
    db.add(oidc_session)
    db.commit()

    # Bereinige alte Sessions (> 10 Minuten)
    cutoff = datetime.utcnow() - timedelta(minutes=10)
    db.query(OIDCSession).filter(OIDCSession.created_at < cutoff).delete()
    db.commit()

    # Bestimme Redirect-URI
    redirect_uri = (
        settings.oidc_redirect_uri_app if client == "app" else settings.oidc_redirect_uri_web
    )

    # Baue Authorization-URL
    params = {
        "response_type": "code",
        "client_id": settings.oidc_client_id,
        "redirect_uri": redirect_uri,
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": pkce["code_challenge"],
        "code_challenge_method": "S256",
    }

    auth_url = f"{oidc_config['authorization_endpoint']}?{urlencode(params)}"
    return {"url": auth_url}


def _app_error_code(exc: HTTPException) -> str:
    """Kurzer Fehlercode für den Rücksprung in die App (familienhub://auth?error=…)."""
    detail = str(exc.detail)
    if detail == "User not found":
        return "unknown_user"
    if detail == "User account is disabled":
        return "disabled"
    if detail.startswith("Anmeldung abgebrochen"):
        return "cancelled"
    if detail in ("Invalid or expired state", "Session expired"):
        return "expired"
    return "failed"


@router.get("/oidc/callback")
async def oidc_callback(
    request: Request,
    state: Optional[str] = None,
    code: Optional[str] = None,
    error: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """OIDC-Callback.

    Web: Fehler als HTTP-Status. App: jeder Fehler führt per Deep-Link zurück in die App
    (``familienhub://auth?error=…``), damit niemand mit einer JSON-Seite im Browser hängen bleibt.
    """
    oidc_session = (
        db.query(OIDCSession).filter(OIDCSession.state == state).first() if state else None
    )
    client_type = oidc_session.client_type if oidc_session is not None else None
    try:
        if error:
            raise HTTPException(status_code=400, detail=f"Anmeldung abgebrochen: {error}")
        if not code or not state:
            raise HTTPException(status_code=400, detail="code und state erforderlich")
        return await _finish_oidc_login(code, state, request, db)
    except HTTPException as exc:
        if client_type == "app":
            return RedirectResponse(url=f"familienhub://auth?{urlencode({'error': _app_error_code(exc)})}")
        if client_type == "pwa":
            return RedirectResponse(url=f"/?{urlencode({'oidc_error': _app_error_code(exc)})}", status_code=302)
        raise


async def _finish_oidc_login(code: str, state: str, request: Request, db: Session):
    """Code gegen Tokens tauschen, Nutzer zuordnen, Hub-Sitzung ausstellen."""
    if not settings.oidc_issuer or not settings.oidc_client_id:
        raise HTTPException(status_code=501, detail="OIDC not configured")

    # Finde Session anhand state
    oidc_session = db.query(OIDCSession).filter(OIDCSession.state == state).first()
    if not oidc_session:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    # Prüfe Alter der Session (max 10 Minuten)
    if oidc_session.created_at < datetime.utcnow() - timedelta(minutes=10):
        db.delete(oidc_session)
        db.commit()
        raise HTTPException(status_code=400, detail="Session expired")

    # Hole OIDC-Konfiguration
    try:
        oidc_config = await fetch_oidc_config()
        jwks = await fetch_jwks(oidc_config["jwks_uri"])
    except Exception:
        raise HTTPException(status_code=503, detail="OIDC provider unreachable")

    # Tausche Code gegen Tokens
    redirect_uri = (
        settings.oidc_redirect_uri_app
        if oidc_session.client_type == "app"
        else settings.oidc_redirect_uri_web
    )

    try:
        tokens = await exchange_code_for_tokens(
            code=code,
            code_verifier=oidc_session.code_verifier,
            token_endpoint=oidc_config["token_endpoint"],
            redirect_uri=redirect_uri,
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Token exchange failed")

    # Verifiziere ID-Token
    id_token_payload = verify_id_token(
        id_token=tokens["id_token"],
        jwks=jwks,
        expected_nonce=oidc_session.nonce,
        expected_issuer=settings.oidc_issuer,
        expected_audience=settings.oidc_client_id,
    )

    if not id_token_payload:
        raise HTTPException(status_code=401, detail="Invalid ID token")

    # Extrahiere E-Mail (case-insensitive)
    email = id_token_payload.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="No email in ID token")

    email = email.lower()

    # Finde oder erstelle Nutzer
    user = db.query(User).filter(User.email.ilike(email)).first()

    if not user:
        if not settings.oidc_auto_create:
            raise HTTPException(status_code=403, detail="User not found")

        # Auto-Create: Erstelle neuen Partner-Account
        username = email.split("@")[0]
        # Stelle sicher, dass Username einzigartig ist
        base_username = username
        counter = 1
        while db.query(User).filter(User.username == username).first():
            username = f"{base_username}{counter}"
            counter += 1

        user = User(
            username=username,
            email=email,
            hashed_password=get_password_hash(secrets.token_urlsafe(32)),  # Zufälliges Passwort
            full_name=id_token_payload.get("name", username),
            role="partner",
            is_admin=False,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is disabled")

    # Eingeladene Person meldet sich über den Anmeldedienst an: Einladung gilt als eingelöst
    from app.models.invite import Invite

    db.query(Invite).filter(Invite.user_id == user.id, Invite.used_at.is_(None), Invite.revoked_at.is_(None)) \
        .update({Invite.used_at: datetime.utcnow()}, synchronize_session=False)
    db.commit()

    # Aktualisiere last_login
    user.last_login = datetime.utcnow()
    db.commit()

    # Lösche OIDC-Session
    db.delete(oidc_session)
    db.commit()

    if oidc_session.client_type == "web":
        # Web: Cookies auf genau die Antwort setzen, die zurückgeht (vorher gingen sie verloren)
        access = create_access_token(data={"sub": user.username})
        refresh = create_refresh_token(user.id, db, request)
        redirect = RedirectResponse(url=(resolve_prefix(request) or "") + "/", status_code=302)
        set_auth_cookies(redirect, access, refresh)
        return redirect

    else:
        # App: Erzeuge Exchange-Code
        exchange_code = secrets.token_urlsafe(32)
        exchange_record = OIDCExchangeCode(
            code=exchange_code,
            user_id=user.id,
            used=False,
            app_challenge=oidc_session.app_challenge,
        )
        db.add(exchange_record)
        db.commit()

        # Bereinige alte Exchange-Codes (> 2 Minuten)
        cutoff = datetime.utcnow() - timedelta(minutes=2)
        db.query(OIDCExchangeCode).filter(OIDCExchangeCode.created_at < cutoff).delete()
        db.commit()

        # App: Deep-Link; Web-App (pwa): zurück auf die Seite, die den Code eintauscht
        if oidc_session.client_type == "pwa":
            return RedirectResponse(url=f"/?{urlencode({'oidc_code': exchange_code})}", status_code=302)
        return RedirectResponse(url=f"familienhub://auth?code={exchange_code}")


def _challenge_of(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


def _valid_challenge(challenge: Optional[str]) -> Optional[str]:
    if challenge is None:
        return None
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", challenge):
        raise HTTPException(status_code=400, detail="Invalid challenge")
    return challenge


@router.post("/oidc/exchange", response_model=TokenResponse)
async def oidc_exchange(data: OIDCExchangeRequest, request: Request, db: Session = Depends(get_db)):
    """Tausche Exchange-Code gegen Hub-Tokens (nur für App)."""
    exchange_record = (
        db.query(OIDCExchangeCode)
        .filter(OIDCExchangeCode.code == data.code, OIDCExchangeCode.used == False)  # noqa: E712
        .first()
    )

    if not exchange_record:
        raise HTTPException(status_code=401, detail="Invalid or expired exchange code")

    # PKCE-Bindung: Wurde beim Start ein Hash mitgegeben, braucht das Einlösen das passende Geheimnis.
    # So nützt ein von einer fremden App abgefangener familienhub://-Rücksprung nichts.
    if exchange_record.app_challenge:
        given = _challenge_of(data.verifier) if data.verifier else None
        if not given or not hmac.compare_digest(given, exchange_record.app_challenge):
            exchange_record.used = True  # nach einem Fehlversuch verbrannt
            db.commit()
            raise HTTPException(status_code=401, detail="Invalid or expired exchange code")

    # Prüfe Alter (max 60 Sekunden)
    if exchange_record.created_at < datetime.utcnow() - timedelta(seconds=60):
        db.delete(exchange_record)
        db.commit()
        raise HTTPException(status_code=401, detail="Exchange code expired")

    # Markiere als verwendet
    exchange_record.used = True
    db.commit()

    # Lade Nutzer
    user = db.query(User).filter(User.id == exchange_record.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    # Erzeuge Tokens
    access = create_access_token(data={"sub": user.username})
    refresh = create_refresh_token(user.id, db, request)

    return {
        "access_token": access,
        "token_type": "bearer",
        "refresh_token": refresh,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_admin": user.is_admin,
        },
    }



# --- Persönliche Zugangsschlüssel (z. B. Sprachassistenten) ---


class ApiTokenCreate(BaseModel):
    name: str
    # None = unrestricted (as before). Otherwise scope names or the preset "voice"; such keys only reach /api/voice.
    scopes: Optional[List[str]] = None


def _token_payload(t) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "hint": t.hint,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
        "scopes": t.scope_list,
    }


@router.get("/api-tokens")
async def list_api_tokens(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Eigene, nicht widerrufene Schlüssel (ohne Klartext)."""
    from app.models.api_token import ApiToken

    tokens = (
        db.query(ApiToken)
        .filter(ApiToken.user_id == current_user.id, ApiToken.revoked_at.is_(None))
        .order_by(ApiToken.created_at.desc())
        .all()
    )
    return [_token_payload(t) for t in tokens]


@router.post("/api-tokens", status_code=status.HTTP_201_CREATED)
async def create_api_token(data: ApiTokenCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Neuer Schlüssel für die eigene Person. Der Klartext steht nur in dieser Antwort."""
    from app.models.api_token import ApiToken

    name = data.name.strip()[:60]
    if not name:
        raise HTTPException(status_code=400, detail="Name fehlt")
    scopes = None
    if data.scopes is not None:
        from app.models.api_token import SCOPE_PRESETS, VOICE_SCOPES

        wanted = []
        for s in data.scopes:
            wanted.extend(SCOPE_PRESETS.get(s, (s,)))
        unknown = [s for s in wanted if s not in VOICE_SCOPES]
        if unknown or not wanted:
            raise HTTPException(status_code=400, detail=f"Unknown scope: {', '.join(unknown) or '(none)'}")
        scopes = " ".join(dict.fromkeys(wanted))
    raw = ApiToken.generate()
    token = ApiToken(user_id=current_user.id, name=name, token_hash=ApiToken.hash(raw), hint=raw[:8], scopes=scopes)
    db.add(token)
    db.commit()
    db.refresh(token)
    return {**_token_payload(token), "token": raw}


@router.delete("/api-tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_token(token_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Eigenen Schlüssel widerrufen. Fremde → 404."""
    from app.models.api_token import ApiToken

    token = (
        db.query(ApiToken)
        .filter(ApiToken.id == token_id, ApiToken.user_id == current_user.id, ApiToken.revoked_at.is_(None))
        .first()
    )
    if not token:
        raise HTTPException(status_code=404, detail="Schlüssel nicht gefunden")
    token.revoked_at = datetime.utcnow()
    db.commit()
