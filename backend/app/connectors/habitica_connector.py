"""Nativer persönlicher Aufgabenadapter: frische Reads, minimale Writes, kein Replay."""
from hashlib import sha256
import json
from uuid import UUID

import httpx
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.core.crypto import decrypt
from app.core.logging_config import get_logger
from app.models.habitica import HabiticaAccount, HabiticaSelection, HabiticaOperation
from app.plugins.base import get_setting

logger = get_logger("connector.habitica")
TYPES = {"todo", "daily", "habit", "reward"}
COMMON = {"text", "notes", "alias", "attribute", "priority", "tags", "reminders"}
FIELDS = {"habit": {"up", "down", "frequency"},
          "daily": {"frequency", "everyX", "startDate", "repeat", "daysOfMonth", "weeksOfMonth", "streak", "collapseChecklist"},
          "todo": {"date", "collapseChecklist"}, "reward": {"value"}}


def account_reference(account):
    return f"{account.user_id}:" + sha256(f"{account.server_url}/{account.remote_user_id}".encode()).hexdigest()[:24]


def writes_allowed(account):
    # Betreiberfreigabe ist absichtlich NICHT Teil der persönlichen Konto-API.
    return f"{account.server_url}|{account.remote_user_id}" in str(get_setting("HABITICA_NATIVE_WRITE_ACCOUNTS", "")).split(",")


def identifier(value):
    try:
        if str(UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(422, "Native IDs müssen kanonische UUIDs sein") from exc
    return value


async def remote_request(account, method, path, **kwargs):
    from app.routers.habitica import active, server_url
    if not active() or account.server_url != server_url():
        raise HTTPException(409, "Habitica ist deaktiviert oder der Server wurde geändert")
    if method != "GET" and not writes_allowed(account):
        raise HTTPException(409, "Native Schreibfreigabe fehlt: Betreiber muss zuerst den Single-Writer-Übergang prüfen")
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        response = await client.request(method, f"{account.server_url}/api/v3/{path}", headers={
            "x-api-user": account.remote_user_id, "x-api-key": decrypt(account.api_key_enc), "x-client": "familienhub"}, **kwargs)
        response.raise_for_status()
        if response.is_redirect:
            raise ValueError("Weiterleitung nicht bestätigt")
        body = response.json()
        if not body.get("success"):
            raise ValueError("Habitica hat die Anfrage nicht bestätigt")
        return body["data"]



def habitica_day(value):
    """Habitica stores a to-do's day as a UTC timestamp (e.g. 22:00Z the evening before); the app needs the day."""
    if not value or not isinstance(value, str):
        return None
    if len(value) == 10:
        return value
    from datetime import datetime

    from app.core.timeutil import local_tz

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return (dt.astimezone(local_tz()) if dt.tzinfo else dt).date().isoformat()

class HabiticaConnector:
    def __init__(self, user_id, db):
        self.user_id, self.db = user_id, db
        self.account = db.get(HabiticaAccount, user_id)
        self.account_ref = account_reference(self.account) if self.account else f"{user_id}:unconfigured"

    @property
    def is_configured(self):
        from app.routers.habitica import active, server_url
        return bool(self.account and active() and self.account.server_url == server_url())

    @property
    def accepts_assigned(self):
        """Can this account take a task someone else assigned right now (account, server and write release)?"""
        return bool(self.is_configured and writes_allowed(self.account) and not self.account.pending_operation)

    def require(self, write=False):
        # Re-read identity/key and config at every boundary, not a cached client.
        if self.account:
            self.db.refresh(self.account)
        if not self.is_configured or account_reference(self.account) != self.account_ref:
            raise HTTPException(409, "Kein aktives persönliches Habitica-Konto")
        if write and not writes_allowed(self.account):
            raise HTTPException(409, "Betreiberfreigabe nach geprüftem Single-Writer-Übergang fehlt")
        return self.account

    def task(self, remote):
        self.owned(remote)
        return {"uid": remote.get("id", remote.get("_id")), "title": remote.get("text", ""),
                "notes": remote.get("notes", ""), "due": habitica_day(remote.get("date")) if remote["type"] == "todo" else None,
                "priority": None, "done": bool(remote.get("completed", False)),
                "list": {"name": "Habitica", "kind": "personal"}, "assignee": self.user_id,
                "created_by": None, "native": remote, "etag": remote.get("updatedAt"),
                "actions": self.actions(remote), "provider": "habitica", "account": self.account_ref}

    def owned(self, remote):
        if remote.get("userId") != self.require().remote_user_id or remote.get("type") not in TYPES:
            raise HTTPException(403, "Aufgabe gehört nicht zum eigenen Habitica-Konto")

    def actions(self, remote):
        if not writes_allowed(self.account) or self.account.pending_operation:
            return []
        kind = remote["type"]
        if kind == "habit":
            return [d for d in ("up", "down") if remote.get(d, False)]
        if kind == "reward":
            return ["up"]
        return ["down" if remote.get("completed") else "up"]

    async def get_task(self, uid):
        account = self.require()
        try:
            remote = await remote_request(account, "GET", f"tasks/{identifier(uid)}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise HTTPException(404, "Habitica-Aufgabe wurde entfernt; Auswahl bleibt bis zum bewussten Entfernen erhalten") from exc
            raise HTTPException(503, "Habitica-Aufgabe nicht lesbar") from exc
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise HTTPException(503, "Habitica-Aufgabe nicht lesbar") from exc
        self.owned(remote)
        return remote

    async def options(self):
        account = self.require()
        try:
            user = await remote_request(account, "GET", "user")
            if user.get("id", user.get("_id")) != account.remote_user_id:
                raise HTTPException(403, "Habitica-Konto stimmt nicht mehr überein")
            preferences = user.get("preferences", {})
            return {"tags": [{"id": t["id"], "name": t["name"]} for t in user.get("tags", [])],
                    "dayStart": preferences.get("dayStart"), "timezoneOffset": preferences.get("timezoneOffset"),
                    "writes_enabled": bool(writes_allowed(account) and not account.pending_operation)}
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise HTTPException(503, "Native Habitica-Optionen nicht lesbar") from exc

    async def available_tasks(self, include_done=False):
        if not self.is_configured:
            return {"status": "not_configured", "error": None, "items": []}
        try:
            account = self.require()
            tasks = await remote_request(account, "GET", "tasks/user")
            if include_done:
                tasks += await remote_request(account, "GET", "tasks/user", params={"type": "completedTodos"})
            by_id = {t.get("id", t.get("_id")): t for t in tasks if t.get("userId") == account.remote_user_id and t.get("type") in TYPES}
            selected = {s.remote_id for s in self.db.query(HabiticaSelection).filter_by(user_id=self.user_id, account_ref=self.account_ref)}
            return {"status": "ok", "error": None, "items": [{**self.task(t), "selected": uid in selected} for uid, t in by_id.items()]}
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("Habitica-Aufgaben nicht lesbar (%s)", type(exc).__name__, exc_info=True)
            return {"status": "unavailable", "error": "Habitica ist nicht erreichbar", "items": []}

    async def get_lists(self):
        return {"status": "ok" if self.is_configured else "not_configured", "error": None,
                "lists": [{"id": "personal", "display_name": "Habitica: eigene Auswahl"}] if self.is_configured else []}

    async def select_task(self, uid, selected):
        self.require()
        key = {"user_id": self.user_id, "account_ref": self.account_ref, "remote_id": identifier(uid)}
        existing = self.db.get(HabiticaSelection, key)
        if selected:
            await self.get_task(uid)  # Nie eine fremde Remote-ID binden.
            if not existing:
                self.db.add(HabiticaSelection(**key))
        elif existing:
            self.db.delete(existing)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()  # Gleichzeitige identische Auswahl ist bereits erfüllt.
        return {"selected": selected, "uid": uid, "provider": "habitica", "account": self.account_ref}

    async def get_tasks(self, view="all", include_done=False):
        if not self.is_configured:
            return {"status": "not_configured", "error": None, "items": []}
        if view not in ("all", "mine"):
            return {"status": "ok", "error": None, "items": []}
        listed = await self.available_tasks(include_done=include_done)
        if listed["status"] != "ok":
            return listed
        items = []
        for item in listed["items"]:
            remote = item.get("native") or {}
            if include_done or not remote.get("completed") or remote.get("type") == "daily":
                items.append({k: v for k, v in item.items() if k != "selected"})
        return {"status": "ok", "error": None, "items": items}

    async def mutation(self, operation_id, verb, target, body, perform):
        account = self.require(write=True)
        operation_id = identifier(str(operation_id))
        key = sha256(f"{self.account_ref}/{operation_id}".encode()).hexdigest()
        fingerprint = sha256(json.dumps([verb, target, body], sort_keys=True).encode()).hexdigest()
        operation = self.db.get(HabiticaOperation, key)
        if operation:
            if operation.fingerprint != fingerprint:
                raise HTTPException(409, "Operationsschlüssel wurde für eine andere Aktion verwendet")
            if operation.state != "confirmed":
                raise HTTPException(409, "Aktion unbestätigt; nicht wiederholen, Betreiberprüfung erforderlich")
            return operation.result
        # ponytail: ein DB-Lock je Konto, objektweise erst bei gemessenem Durchsatzbedarf.
        claimed = self.db.query(HabiticaAccount).filter_by(user_id=self.user_id, server_url=account.server_url,
            remote_user_id=account.remote_user_id, pending_operation=None).update({"pending_operation": key})
        if not claimed:
            self.db.rollback()
            raise HTTPException(409, "Eine Kontoaktion läuft oder ist unbestätigt; nicht erneut senden")
        operation = HabiticaOperation(key=key, user_id=self.user_id, account_ref=self.account_ref,
                                      fingerprint=fingerprint, state="pending")
        self.db.add(operation)
        self.db.commit()  # Reservierung vor JEDEM Remote-Write, auch über mehrere Worker.
        try:
            result = await perform()
            operation.state, operation.result = "confirmed", result
            account.pending_operation = None
            self.db.commit()
            return result
        except Exception as exc:
            # Kein Replay, auch bei verlorener DB-Bestätigung. Persistierter pending-Lock bleibt im Zweifel stehen.
            self.db.rollback()
            logger.warning("Habitica-Aktion unbestätigt (%s)", type(exc).__name__, exc_info=True)
            raise HTTPException(409, "Aktion unbestätigt. Remotezustand prüfen; nicht blind wiederholen") from exc

    def fields(self, native, kind):
        from app.schemas.habitica import NativeFields
        from pydantic import ValidationError
        try:
            parsed = NativeFields.model_validate(native).model_dump(exclude_unset=True)
        except ValidationError as exc:
            raise HTTPException(422, "Ungültige native Optionen") from exc
        if set(parsed) - COMMON - FIELDS[kind] - {"type"}:
            raise HTTPException(422, "Option passt nicht zum Habitica-Aufgabentyp")
        if "frequency" in parsed:
            allowed = {"daily", "weekly", "monthly"} if kind == "habit" else {"daily", "weekly", "monthly", "yearly"}
            if parsed["frequency"] not in allowed:
                raise HTTPException(422, "Ungültige native Wiederholung")
        return parsed

    async def validate_tags(self, body):
        if body.get("tags"):
            own = {tag["id"] for tag in (await self.options())["tags"]}
            if set(body["tags"]) - own:
                raise HTTPException(403, "Tags gehören nicht zum eigenen Habitica-Konto")

    async def create_task(self, title, notes=None, due=None, native=None, operation_id=None, **kwargs):
        self.require(write=True)
        if kwargs.get("assignee_id") not in (None, self.user_id) or kwargs.get("list_kind") or kwargs.get("rotation"):
            raise HTTPException(422, "Habitica-Aufgaben gehören ausschließlich zum eigenen Konto")
        native = native or {"type": "todo"}
        kind = native.get("type", "todo")
        if kind not in TYPES:
            raise HTTPException(422, "Ungültiger Habitica-Aufgabentyp")
        body = self.fields({**native, "text": title, "type": kind}, kind)
        if notes is not None:
            body["notes"] = notes
        if due is not None:
            if kind != "todo":
                raise HTTPException(422, "Fälligkeit gehört nur zu nativen Todos")
            body["date"] = due
        await self.validate_tags(body)
        async def perform():
            remote = await remote_request(self.require(write=True), "POST", "tasks/user", json=body)
            task = self.task(remote)
            identifier(task["uid"])
            key = {"user_id": self.user_id, "account_ref": self.account_ref, "remote_id": task["uid"]}
            if not self.db.get(HabiticaSelection, key):
                self.db.add(HabiticaSelection(**key))
            return task
        return await self.mutation(operation_id, "create", "new", body, perform)

    async def update_task(self, uid, native=None, expected_version=None, operation_id=None, **updates):
        remote = await self.get_task(uid)
        if expected_version is None or remote.get("updatedAt") != expected_version:
            raise HTTPException(409, "Aufgabe wurde geändert; vor dem Bearbeiten neu laden")
        native = dict(native or {})
        if "type" in native:
            raise HTTPException(422, "Native Aufgabentypen sind nach Anlage unveränderlich")
        for source, target in {"title": "text", "notes": "notes", "due": "date"}.items():
            if source in updates:
                native[target] = updates[source]
        if "priority" in updates:
            raise HTTPException(422, "Native Schwierigkeit über native.priority angeben")
        body = self.fields(native, remote["type"])
        await self.validate_tags(body)
        async def perform():
            # Native 5.51 merged nichtleere Monatsarrays indexweise. Erst explizit leeren,
            # sonst blieben bei Verkleinerung alte Termine übrig. Kein Replay bei Teilerfolg.
            clear = {key: [] for key in ("daysOfMonth", "weeksOfMonth")
                     if key in body and body[key] and len(body[key]) < len(remote.get(key, []))}
            if clear:
                await remote_request(self.require(write=True), "PUT", f"tasks/{identifier(uid)}", json=clear)
            result = await remote_request(self.require(write=True), "PUT", f"tasks/{identifier(uid)}", json=body)
            return self.task(result)
        return await self.mutation(operation_id, "update", uid, body, perform)

    async def action(self, uid, action, operation_id, **options):
        remote = await self.get_task(uid)
        body = options.get("fields", {})
        if action in ("up", "down"):
            if action not in self.actions(remote):
                raise HTTPException(409, "Diese native Punktrichtung ist nicht erlaubt")
            path, method = f"tasks/{uid}/score/{action}", "POST"
            body = None
        elif action in ("checklist_add", "checklist_edit", "checklist_delete"):
            if remote["type"] not in ("todo", "daily"):
                raise HTTPException(422, "Checklisten gehören zu Todo oder Daily")
            if set(body) - {"text", "completed"} or ("text" in body and (not isinstance(body["text"], str) or not body["text"].strip())) or ("completed" in body and type(body["completed"]) is not bool):
                raise HTTPException(422, "Ungültige Checklistenänderung")
            path, method = f"tasks/{uid}/checklist", "POST"
            if action != "checklist_add":
                item_id = identifier(options.get("item_id"))
                if not any(i.get("id") == item_id for i in remote.get("checklist", [])):
                    raise HTTPException(404, "Checklistenpunkt fehlt")
                path += f"/{item_id}"
                method = "PUT" if action == "checklist_edit" else "DELETE"
            elif not body.get("text"):
                raise HTTPException(422, "Checklistenpunkt benötigt Text")
        elif action == "checklist_move":
            if remote["type"] not in ("todo", "daily"):
                raise HTTPException(422, "Checklisten gehören zu Todo oder Daily")
            item_id = identifier(options.get("item_id"))
            checklist = remote.get("checklist", [])
            position = body.get("position")
            if set(body) != {"position"} or type(position) is not int or not 0 <= position < len(checklist):
                raise HTTPException(422, "Ungültige Checklistenposition")
            item = next((item for item in checklist if item.get("id") == item_id), None)
            if item is None:
                raise HTTPException(404, "Checklistenpunkt fehlt")
            ordered = [entry for entry in checklist if entry.get("id") != item_id]
            ordered.insert(position, item)
            path, method, body = f"tasks/{uid}", "PUT", {"checklist": ordered}
        elif action == "move":
            position = body.get("position")
            if set(body) != {"position"} or type(position) is not int or position < 0:
                raise HTTPException(422, "Position muss eine nichtnegative Ganzzahl sein")
            path, method, body = f"tasks/{uid}/move/to/{position}", "POST", None
        else:
            raise HTTPException(422, "Unbekannte native Aktion")
        async def perform():
            await remote_request(self.require(write=True), method, path, **({"json": body} if body is not None else {}))
            # Ein erfolgreicher Score ist kein Taskobjekt. Refresh ist read-only; sein Fehler löst keinen zweiten Score aus.
            return {"accepted": True}
        return await self.mutation(operation_id, action, uid, [path, body], perform)

    async def complete_task(self, uid, operation_id=None):
        await self.action(uid, "up", operation_id)
        return self.task(await self.get_task(uid))

    async def delete_task(self, uid, operation_id=None):
        await self.get_task(uid)
        async def perform():
            await remote_request(self.require(write=True), "DELETE", f"tasks/{identifier(uid)}")
            return True
        return await self.mutation(operation_id, "delete", uid, None, perform)
