"""Paperless-Plugin (#30): persönlicher Zugang, Suche, neueste Dokumente, Vorschaubild, Fristen → Erinnerung."""

import json
from datetime import date, timedelta

import httpx
import pytest
import respx

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.paperless import PaperlessAccount
from app.models.reminder import Reminder
from app.models.user import User

PL = "http://paperless.test"
TOKEN = "pl-token-anna"


def _auth(client, name):
    with SessionLocal() as db:
        if not db.query(User).filter(User.username == name).first():
            db.add(User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"), role="partner"))
            db.commit()
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _doc(i, title, frist=None, aufgabe=None):
    fields = []
    if frist:
        fields.append({"field": 1, "value": frist})
    if aufgabe:
        fields.append({"field": 2, "value": aufgabe})
    return {"id": i, "title": title, "created": "2026-10-10", "correspondent": 3, "document_type": 4,
            "tags": [5], "custom_fields": fields}


@pytest.fixture
def pl(monkeypatch):
    monkeypatch.setenv("PAPERLESS_URL", PL)
    monkeypatch.setenv("PAPERLESS_PUBLIC_URL", "https://paperless.example")
    seen = []
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()

        def guard(request):
            seen.append(request)
            if request.headers.get("Authorization") != f"Token {TOKEN}":
                return httpx.Response(401, json={"detail": "Ungültiges Token"})
            return None

        def respond(payload):
            def handler(request):
                return guard(request) or httpx.Response(200, json=payload)
            return handler

        http.get(f"{PL}/api/ui_settings/").mock(side_effect=respond({"user": {"id": 4, "username": "Anna"}}))
        http.get(f"{PL}/api/correspondents/").mock(side_effect=respond({"results": [{"id": 3, "name": "Telekom"}]}))
        http.get(f"{PL}/api/document_types/").mock(side_effect=respond({"results": [{"id": 4, "name": "Rechnung"}]}))
        http.get(f"{PL}/api/tags/").mock(side_effect=respond({"results": [{"id": 5, "name": "Telefon & Internet"}]}))
        http.get(f"{PL}/api/custom_fields/").mock(side_effect=respond({"results": [
            {"id": 1, "name": "Frist", "data_type": "date"}, {"id": 2, "name": "Aufgabe", "data_type": "string"}]}))

        def documents(request):
            bad = guard(request)
            if bad:
                return bad
            q = dict(request.url.params)
            if "custom_field_query" in q:
                soon = (date.today() + timedelta(days=5)).isoformat()
                return httpx.Response(200, json={"count": 1, "results": [_doc(7, "Telekom Rechnung", soon, "Rechnung bezahlen")]})
            if q.get("query") == "telekom":
                return httpx.Response(200, json={"count": 1, "results": [_doc(7, "Telekom Rechnung")]})
            return httpx.Response(200, json={"count": 2, "results": [_doc(9, "Neu"), _doc(8, "Älter")]})

        http.get(f"{PL}/api/documents/").mock(side_effect=documents)
        http.get(f"{PL}/api/documents/7/thumb/").mock(
            side_effect=lambda r: guard(r) or httpx.Response(200, content=b"RIFF0000WEBPVP8 ", headers={"content-type": "image/webp"}))
        http.get(f"{PL}/api/documents/8/thumb/").mock(
            side_effect=lambda r: guard(r) or httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"}))
        yield seen


def _connect(client, h):
    return client.put("/api/paperless/account", headers=h, json={"token": TOKEN})


def test_module_and_not_configured(client, auth, monkeypatch):
    monkeypatch.delenv("PAPERLESS_URL", raising=False)
    assert client.get("/api/modules", headers=auth).json()["modules"]["documents"]["enabled"] is False
    r = client.get("/api/paperless/recent", headers=auth).json()
    assert r["status"] == "not_configured" and r["items"] == []


def test_without_own_token_nothing_is_read(client, pl):
    h = _auth(client, "pl_none")
    r = client.get("/api/paperless/recent", headers=h).json()
    assert r["status"] == "no_account" and r["items"] == []
    assert pl == []  # kein Aufruf an Paperless ohne eigenen Zugang


def test_connect_verifies_and_stores_encrypted(client, pl):
    h = _auth(client, "pl_anna")
    assert client.put("/api/paperless/account", headers=h, json={"token": "falsch"}).status_code == 422
    r = _connect(client, h)
    assert r.status_code == 200 and r.json() == {"connected": True, "username": "Anna"}
    with SessionLocal() as db:
        u = db.query(User).filter(User.username == "pl_anna").first()
        acc = db.get(PaperlessAccount, u.id)
        assert acc.token_enc != TOKEN and acc.remote_username == "Anna"
    assert client.get("/api/paperless/account", headers=h).json() == {"configured": True, "connected": True, "username": "Anna"}
    assert "token" not in json.dumps(client.get("/api/paperless/account", headers=h).json()).lower().replace("connected", "")


def test_recent_and_search_resolve_names(client, pl):
    h = _auth(client, "pl_b")
    _connect(client, h)
    recent = client.get("/api/paperless/recent", headers=h).json()
    assert recent["status"] == "ok" and [d["title"] for d in recent["items"]] == ["Neu", "Älter"]
    hit = client.get("/api/paperless/search?q=telekom", headers=h).json()["items"][0]
    assert hit == {"id": 7, "title": "Telekom Rechnung", "created": "2026-10-10", "correspondent": "Telekom",
                   "document_type": "Rechnung", "tags": ["Telefon & Internet"],
                   "url": "https://paperless.example/documents/7/details", "thumb": "/api/paperless/documents/7/thumb"}
    # Suche nutzt nur das eigene Token
    assert all(r.headers["Authorization"] == f"Token {TOKEN}" for r in pl)


def test_search_needs_text(client, pl):
    h = _auth(client, "pl_c")
    _connect(client, h)
    assert client.get("/api/paperless/search?q=a", headers=h).json()["items"] == []


def test_thumbnail_proxy_only_images(client, pl):
    h = _auth(client, "pl_d")
    _connect(client, h)
    r = client.get("/api/paperless/documents/7/thumb", headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "image/webp"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert client.get("/api/paperless/documents/8/thumb", headers=h).status_code == 502  # kein Bild → nicht durchreichen
    assert client.get("/api/paperless/documents/7/thumb").status_code == 401


def test_deadlines_and_reminder(client, pl):
    h = _auth(client, "pl_e")
    _connect(client, h)
    d = client.get("/api/paperless/deadlines", headers=h).json()
    assert d["status"] == "ok"
    item = d["items"][0]
    assert item["id"] == 7 and item["task"] == "Rechnung bezahlen" and item["deadline"] == (date.today() + timedelta(days=5)).isoformat()
    r = client.post("/api/paperless/deadlines/7/remind", headers=h)
    assert r.status_code == 201
    with SessionLocal() as db:
        rem = db.query(Reminder).filter(Reminder.title == "📄 Rechnung bezahlen").order_by(Reminder.id.desc()).first()
        assert rem is not None and rem.for_family is False and rem.notes.endswith("/documents/7/details")
    # zweimal → kein Duplikat
    assert client.post("/api/paperless/deadlines/7/remind", headers=h).status_code == 200


def test_revoked_token_reports_status(client, pl, monkeypatch):
    h = _auth(client, "pl_f")
    _connect(client, h)
    with SessionLocal() as db:
        u = db.query(User).filter(User.username == "pl_f").first()
        from app.core.crypto import encrypt
        db.get(PaperlessAccount, u.id).token_enc = encrypt("widerrufen")
        db.commit()
    r = client.get("/api/paperless/recent", headers=h).json()
    assert r["status"] == "auth_failed" and r["items"] == []


def test_disconnect(client, pl):
    h = _auth(client, "pl_g")
    _connect(client, h)
    assert client.delete("/api/paperless/account", headers=h).status_code == 200
    assert client.get("/api/paperless/account", headers=h).json()["connected"] is False
