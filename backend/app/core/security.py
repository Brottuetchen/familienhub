"""Authentifizierung & Autorisierung.

Enthält Passwort-Hashing, JWT-Handling, Refresh-Tokens, Rate-Limiting sowie
rollenbasierte FastAPI-Dependencies.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, Iterable, Optional

import bcrypt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from jwt import PyJWTError as JWTError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.core.database import get_db
from app.core.ingress import cookie_path
from app.models.api_token import TOKEN_PREFIX
from app.models.user import (
    ROLE_ADMIN,
    ROLE_CHILD,
    ROLE_GUEST,
    ROLE_PARTNER,
    LoginAttempt,
    RefreshToken,
    User,
)

ALGORITHM = "HS256"

security = HTTPBearer(auto_error=False)

# Rollen-Hierarchie: höhere Zahl = mehr Rechte.
ROLE_LEVEL = {
    ROLE_GUEST: 0,
    ROLE_CHILD: 1,
    ROLE_PARTNER: 2,
    ROLE_ADMIN: 3,
}


# === Passwörter ===

def verify_password(plain_password: str, hashed_password: str) -> bool:
    # bcrypt akzeptiert max. 72 Bytes; identisch zu passlib-erzeugten $2b$-Hashes.
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8")[:72], hashed_password.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


# === JWT ===

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "access"})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def verify_token(token: str, token_type: str = "access") -> Optional[Dict]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        if payload.get("type") != token_type:
            return None
        exp = payload.get("exp")
        if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
            return None
        return payload
    except JWTError:
        return None


def hash_refresh_token(token: str) -> str:
    """Refresh-Tokens liegen nur als SHA-256 in der Datenbank (ein Datenbank-Leck verrät keine Sitzungen)."""
    return hashlib.sha256(token.encode()).hexdigest()


def create_refresh_token(user_id: int, db: Session, request: Request) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    db_token = RefreshToken(
        user_id=user_id,
        token=hash_refresh_token(token),
        expires_at=expires_at,
        user_agent=request.headers.get("user-agent", "unknown"),
        ip_address=request.client.host if request.client else "unknown",
    )
    db.add(db_token)
    db.commit()
    return token


def verify_refresh_token(token: str, db: Session) -> Optional[RefreshToken]:
    db_token = (
        db.query(RefreshToken)
        .filter(RefreshToken.token == hash_refresh_token(token), RefreshToken.revoked == False)  # noqa: E712
        .first()
    )
    if not db_token or db_token.expires_at < datetime.utcnow():
        return None
    return db_token


def revoke_refresh_token(token: str, db: Session) -> bool:
    db_token = db.query(RefreshToken).filter(RefreshToken.token == hash_refresh_token(token)).first()
    if db_token:
        db_token.revoked = True
        db.commit()
        return True
    return False


# === Authentifizierung ===

def authenticate_user(username: str, password: str, db: Session) -> Optional[User]:
    # Usernames are stored lowercase; "Allie" signs in as "allie" (also matches older mixed-case rows)
    name = (username or "").strip().lower()
    user = db.query(User).filter(func.lower(User.username) == name).first()
    if not user or not verify_password(password, user.hashed_password) or not user.is_active:
        return None
    user.last_login = datetime.utcnow()
    db.commit()
    return user


def check_rate_limit(
    username: str, ip_address: str, db: Session, max_attempts: int = 5, window_minutes: int = 15
) -> bool:
    window_start = datetime.utcnow() - timedelta(minutes=window_minutes)
    failed = (
        db.query(LoginAttempt)
        .filter(
            LoginAttempt.username == username,
            LoginAttempt.ip_address == ip_address,
            LoginAttempt.success == False,  # noqa: E712
            LoginAttempt.attempted_at >= window_start,
        )
        .count()
    )
    return failed < max_attempts


def log_login_attempt(username: str, ip_address: str, success: bool, db: Session) -> None:
    db.add(LoginAttempt(username=username, ip_address=ip_address, success=success))
    db.commit()


# === Dependencies ===

def _user_from_api_token(raw: str, db: Session, unauthorized: HTTPException, request: Optional[Request] = None) -> User:
    from app.models.api_token import ApiToken

    token = (
        db.query(ApiToken)
        .filter(ApiToken.token_hash == ApiToken.hash(raw), ApiToken.revoked_at.is_(None))
        .first()
    )
    if not token:
        raise unauthorized
    user = db.query(User).filter(User.id == token.user_id).first()
    if not user or not user.is_active:
        raise unauthorized
    # last_used höchstens einmal pro Minute schreiben
    now = datetime.utcnow()
    if not token.last_used_at or (now - token.last_used_at).total_seconds() > 60:
        token.last_used_at = now
        db.commit()
    if request is not None:
        scopes = token.scope_list
        request.state.api_token_scopes = scopes
        # A scoped key (e.g. for a voice assistant) never reaches the normal API, only /api/voice
        if scopes is not None and not request.url.path.startswith("/api/voice/"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="This access key is limited to voice assistant use")
    return user


def require_scope(scope: str):
    """Dependency-Factory: an API token with scopes needs ``scope``; sessions and unrestricted keys pass."""

    async def _dep(request: Request, current_user: User = Depends(get_current_user)) -> User:
        scopes = getattr(request.state, "api_token_scopes", None)
        if scopes is not None and scope not in scopes:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Access key lacks scope: {scope}")
        return current_user

    return _dep


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    # Plain def on purpose: FastAPI runs it in the thread pool. As async def, the blocking DB checkout ran on
    # the event loop; with the pool exhausted (many avatars at once) it froze the loop, so no request could
    # finish and give its connection back (prod outage 2026-10-19).
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not credentials:
        raise credentials_exception

    # Persönlicher Zugangsschlüssel (z. B. Sprachassistenten)
    if credentials.credentials.startswith(TOKEN_PREFIX):
        return _user_from_api_token(credentials.credentials, db, credentials_exception, request)

    payload = verify_token(credentials.credentials, token_type="access")
    if not payload:
        raise credentials_exception

    username = payload.get("sub")
    if not username:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled")
    _remember_language(request, user, db)
    return user


def _remember_language(request: Request, user: User, db: Session) -> None:
    """The app sends its language with every request; push texts (#24) use the last one seen."""
    from app.core.i18n import parse_accept_language

    lang = parse_accept_language(request.headers.get("x-app-language") or request.headers.get("accept-language"))
    if lang and lang != getattr(user, "language", None):
        user.language = lang
        try:
            db.commit()
        except Exception:  # noqa: BLE001 – never fail a request over this
            db.rollback()


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user


def require_roles(*roles: str):
    """Dependency-Factory: erlaubt nur die angegebenen Rollen."""

    allowed: Iterable[str] = set(roles)

    async def _dep(current_user: User = Depends(get_current_user)) -> User:
        user_role = current_user.role or (ROLE_ADMIN if current_user.is_admin else ROLE_PARTNER)
        if user_role not in allowed and not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(sorted(allowed))}",
            )
        return current_user

    return _dep


def require_min_role(min_role: str):
    """Dependency-Factory: erlaubt Rollen ab einem Mindest-Level."""

    threshold = ROLE_LEVEL.get(min_role, 0)

    async def _dep(current_user: User = Depends(get_current_user)) -> User:
        user_role = current_user.role or (ROLE_ADMIN if current_user.is_admin else ROLE_PARTNER)
        level = ROLE_LEVEL.get(user_role, 0)
        if current_user.is_admin:
            level = ROLE_LEVEL[ROLE_ADMIN]
        if level < threshold:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires at least role: {min_role}",
            )
        return current_user

    return _dep


async def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if not (current_user.is_admin or current_user.role == ROLE_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required"
        )
    return current_user


# === Cookies ===

def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    path = cookie_path()
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path=path,
        max_age=settings.access_token_expire_minutes * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path=path,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(key="access_token", path=cookie_path())
    response.delete_cookie(key="refresh_token", path=cookie_path())


# === Aktions-Token für Knöpfe in Mitteilungen ===

def create_reminder_action_token(reminder_id: int, user_id: int, days: int = 3) -> str:
    """Kurzlebig, nur für eine Erinnerung und eine Person (Knöpfe „Erledigt“, „Später“)."""
    payload = {"typ": "reminder_action", "rid": reminder_id, "uid": user_id,
               "exp": datetime.utcnow() + timedelta(days=days)}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def verify_reminder_action_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None
    if payload.get("typ") != "reminder_action":
        return None
    return payload


def revoke_all_refresh_tokens(user_id: int, db: Session, keep: Optional[str] = None) -> int:
    """Alle Sitzungen einer Person beenden (z. B. nach Passwortänderung); optional eine behalten."""
    q = db.query(RefreshToken).filter(RefreshToken.user_id == user_id, RefreshToken.revoked == False)  # noqa: E712
    if keep:
        q = q.filter(RefreshToken.token != hash_refresh_token(keep))
    n = q.update({RefreshToken.revoked: True}, synchronize_session=False)
    db.commit()
    return n
