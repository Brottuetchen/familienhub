"""Plugin and theme store (admin only, ``docs/store.md``).

- ``GET /api/admin/store``: entries of the official index and of the extra sources, merged, with a ``verified``
  flag and the install state (``available`` / ``installed`` / ``update`` / ``conflict``). An unreachable source
  gives an empty list plus a ``status``, never an error.
- ``POST /api/admin/store/inspect``: what installing an entry would do (plugin: manifest, settings form; theme: colours).
- ``POST /api/admin/store/install``: install or update exactly the commit the index pins (never a newer one).
- ``GET|POST /api/admin/store/sources``, ``DELETE /api/admin/store/sources/{id}``: extra GitHub sources.
- ``GET /api/admin/store/screenshot/...``: a screenshot, proxied from the allow-listed host.
"""

from __future__ import annotations

from typing import Any, Dict

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.core.database import get_db
from app.core.i18n import request_language
from app.core.logging_config import get_logger
from app.core.security import require_min_role
from app.models.store_source import StoreSource
from app.models.user import ROLE_ADMIN, User
from app.plugins import github, installer
from app.routers import themes as themes_router
from app.store import index as idx
from app.store import service

logger = get_logger("router.store")
audit = get_logger("store.audit")
router = APIRouter(prefix="/api/admin/store", tags=["store"])
admin_only = require_min_role(ROLE_ADMIN)


class EntryRef(BaseModel):
    source: str = Field(min_length=1, max_length=32)
    type: str = Field(pattern="^(plugin|theme)$")
    id: str = Field(min_length=1, max_length=64)


class InstallRequest(EntryRef):
    sha: str = Field(min_length=40, max_length=40)  # the commit the admin reviewed
    settings: Dict[str, Any] = Field(default_factory=dict, max_length=40)
    acknowledge_unverified: bool = False


class SourceRequest(BaseModel):
    url: str = Field(min_length=1, max_length=300)
    acknowledge: bool = False


async def _entry(db: Session, ref: EntryRef):
    try:
        return await service.find(db, ref.source, ref.type, ref.id)
    except LookupError as exc:
        raise HTTPException(404, "Eintrag nicht gefunden") from exc


@router.get("")
async def list_store(request: Request, refresh: bool = False, db: Session = Depends(get_db),
                     _: User = Depends(admin_only)):
    return await service.listing(db, request_language(request), refresh)


@router.post("/inspect")
async def inspect(ref: EntryRef, request: Request, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    source, entry = await _entry(db, ref)
    lang = request_language(request)
    base = {"type": entry.type, "source": source.key, "verified": source.verified, "sha": entry.sha,
            "short_sha": entry.sha[:7], "compatible": idx.optional_hub_ok(entry, service.__version__)}
    try:
        if entry.type == "plugin":
            if not settings.plugin_install_enabled:
                raise HTTPException(403, "Die Plugin-Installation ist abgeschaltet (PLUGIN_INSTALL_ENABLED)")
            preview = await installer.inspect_plugin(entry.repo, lang, db, pin=(entry.sha, entry.path),
                                                     expect_id=entry.id)
            return {**base, **preview}
        theme = await themes_router.fetch_theme(service.theme_url(entry))
        return {**base, "theme": theme}
    except ValueError as exc:  # also GitHubError, InstallError
        raise HTTPException(422, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(422, "GitHub nicht erreichbar") from exc


@router.post("/install")
async def install(data: InstallRequest, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(admin_only)):
    source, entry = await _entry(db, data)
    if not source.verified and not data.acknowledge_unverified:
        raise HTTPException(422, "Dieser Eintrag stammt aus einer ungeprüften Quelle. Bitte die Warnung bestätigen")
    if data.sha != entry.sha:
        raise HTTPException(409, "Der Store-Eintrag hat sich geändert. Bitte die Liste neu laden und erneut prüfen")
    if not idx.optional_hub_ok(entry, service.__version__):
        raise HTTPException(422, f"Der Eintrag braucht Familienhub {entry.min_hub_version} oder neuer")
    audit.warning("Store: %s %s aus Quelle %s (Commit %s, Nutzer %s)", entry.type, entry.id, source.key,
                  entry.sha[:7], user.id)
    if entry.type == "plugin":
        if not settings.plugin_install_enabled:
            raise HTTPException(403, "Die Plugin-Installation ist abgeschaltet (PLUGIN_INSTALL_ENABLED)")
        try:
            result = await installer.install_plugin(request.app, db, user.id, entry.repo, entry.sha, data.settings,
                                                    folder=entry.path, expect_id=entry.id, store_source=source.key)
        except ValueError as exc:  # also GitHubError, ArchiveError, InstallError
            raise HTTPException(422, str(exc)) from exc
        except OSError as exc:
            logger.warning("Store: file error during install: %s", exc.__class__.__name__)
            raise HTTPException(500, "Dateifehler bei der Installation. Einzelheiten stehen im Protokoll") from exc
        from app.models.installed_plugin import InstalledPlugin

        row = db.get(InstalledPlugin, result["id"])
        return {**result, "type": "plugin", "plugin": installer.installed_view(row, request_language(request))}
    try:
        theme = await themes_router.fetch_theme(service.theme_url(entry))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(422, "GitHub nicht erreichbar") from exc
    existing = db.query(themes_router.Theme).filter(themes_router.Theme.store_id == entry.id).first()
    row = themes_router.save_theme(db, user.id, theme, service.theme_url(entry), {
        "id": entry.id, "source": source.key, "sha": entry.sha, "version": entry.version})
    return {"type": "theme", "id": entry.id, "version": entry.version, "sha": entry.sha, "updated": existing is not None,
            "theme": themes_router._custom(row)}  # noqa: SLF001


# --- Extra sources ---

@router.get("/sources")
async def list_sources(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    return {"items": [service.source_view(s, d) for s, d in await service.load_all(db)]}


@router.post("/sources", status_code=201)
async def add_source(data: SourceRequest, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    if not data.acknowledge:
        raise HTTPException(422, "Bitte bestätigen, dass die Quelle nicht von den Maintainern geprüft ist")
    try:
        repo_url = service.normalise_repo_url(data.url)
        index_url = service.custom_index_url(repo_url)
    except ValueError as exc:  # GitHubError
        raise HTTPException(422, str(exc)) from exc
    if db.query(StoreSource).filter(StoreSource.repo_url == repo_url).first():
        raise HTTPException(409, "Diese Quelle gibt es schon")
    if db.query(StoreSource).count() >= service.MAX_CUSTOM_SOURCES:
        raise HTTPException(422, f"Höchstens {service.MAX_CUSTOM_SOURCES} eigene Quellen")
    probe = service.Source("probe", repo_url, index_url, False)
    fetched = await service.fetch_index(probe)
    if fetched.status == "unreachable":
        raise HTTPException(422, "Die Quelle ist gerade nicht erreichbar")
    if fetched.status != "ok":
        raise HTTPException(422, "Im Repository liegt keine gültige index.json (siehe docs/store.md)")
    ref = github.parse_repo_url(repo_url)
    row = StoreSource(repo_url=repo_url, name=(fetched.name or f"{ref.owner}/{ref.repo}")[:80], added_by=user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    audit.warning("Store: eigene Quelle %s hinzugefügt (Nutzer %s)", repo_url, user.id)
    source = next(s for s in service.sources(db) if s.db_id == row.id)
    service.clear_cache()
    return service.source_view(source, await service.load(source))


@router.delete("/sources/{source_id}")
async def delete_source(source_id: int, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    row = db.get(StoreSource, source_id)
    if row is None:
        raise HTTPException(404, "Quelle nicht gefunden")
    db.delete(row)
    db.commit()
    audit.warning("Store: eigene Quelle %s entfernt (Nutzer %s)", row.repo_url, user.id)
    return {"deleted": True}


# --- Screenshots ---

@router.get("/screenshot/{source}/{kind}/{entry_id}/{n}")
async def screenshot(source: str, kind: str, entry_id: str, n: int, db: Session = Depends(get_db),
                     _: User = Depends(admin_only)):
    try:
        body, mime = await service.screenshot(db, source, kind, entry_id, n)
    except LookupError as exc:
        raise HTTPException(404, "Bild nicht gefunden") from exc
    return Response(body, media_type=mime, headers={
        "Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'"})
