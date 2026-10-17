"""Persönlicher Habitica-Zugang; kein Export und keine CalDAV-Schattenobjekte."""
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.crypto import encrypt
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.habitica import HabiticaAccount
from app.models.user import User
from app.schemas import CanonicalUUID
from app.plugins.base import get_setting

router = APIRouter(prefix="/api/habitica", tags=["habitica"])


def server_url():
    return str(get_setting("HABITICA_URL", "")).rstrip("/")


def active():
    from app.plugins.registry import plugin_registry
    return bool(plugin_registry.get("habitica").active)


def account_payload(account):
    from app.connectors.habitica_connector import account_reference, writes_allowed
    configured = bool(account and active() and account.server_url == server_url())
    return {"configured": configured, "remote_user_id": account.remote_user_id if account else None,
            "account": account_reference(account) if account else None,
            "server_url": server_url(), "has_api_key": bool(account and account.api_key_enc), "active": active(),
            "writes_enabled": bool(configured and writes_allowed(account) and not account.pending_operation),
            "unconfirmed_operation": bool(account and account.pending_operation)}


class AccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    remote_user_id: CanonicalUUID
    api_key: str = Field(min_length=1, max_length=1000)


@router.get("/account")
def get_account(response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return account_payload(db.get(HabiticaAccount, user.id))


@router.put("/account")
async def put_account(data: AccountRequest, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.connectors.habitica_connector import remote_request
    url = urlsplit(server_url())
    if not active() or url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise HTTPException(409, "Bitte zuerst eine HTTPS-Adresse für das Habitica-Plugin konfigurieren")
    account = db.get(HabiticaAccount, user.id)
    if account and account.pending_operation:
        raise HTTPException(409, "Unbestätigte Aktion: Konto erst nach Betreiberprüfung ändern")
    candidate = HabiticaAccount(user_id=user.id, server_url=server_url(),
                               remote_user_id=str(data.remote_user_id), api_key_enc=encrypt(data.api_key))
    try:
        remote = await remote_request(candidate, "GET", "user")
        if remote.get("id", remote.get("_id")) != candidate.remote_user_id:
            raise HTTPException(403, "Habitica-Konto konnte nicht bestätigt werden")
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise HTTPException(409, "Habitica-Zugang konnte nicht geprüft werden") from exc
    if account is None:
        account = candidate
        db.add(account)
    else:
        claimed = db.query(HabiticaAccount).filter_by(user_id=user.id, pending_operation=None,
            server_url=account.server_url, remote_user_id=account.remote_user_id).update({
                "server_url": candidate.server_url, "remote_user_id": candidate.remote_user_id,
                "api_key_enc": candidate.api_key_enc}, synchronize_session=False)
        if claimed != 1:
            db.rollback()
            raise HTTPException(409, "Konto wurde geändert oder eine native Aktion läuft; neu laden")
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Dieses Habitica-Konto ist bereits zugeordnet") from exc
    response.headers["Cache-Control"] = "no-store"
    return account_payload(account)


@router.get("/tasks")
async def list_tasks(response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.connectors.habitica_connector import HabiticaConnector
    response.headers["Cache-Control"] = "no-store"
    return await HabiticaConnector(user.id, db).available_tasks(include_done=True)


@router.get("/options")
async def native_options(response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.connectors.habitica_connector import HabiticaConnector
    response.headers["Cache-Control"] = "no-store"
    return await HabiticaConnector(user.id, db).options()
