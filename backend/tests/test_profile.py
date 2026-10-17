"""Profil: Anzeigename, Avatar-Farbe, Profilbild (nur JPEG/PNG/WebP, klein, nur angemeldet)."""

import base64

import pytest

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 64


def _auth(client, name, full_name=None):
    with SessionLocal() as db:
        if not db.query(User).filter(User.username == name).first():
            db.add(User(username=name, email=f"{name}@test.de", full_name=full_name,
                        hashed_password=get_password_hash("pw-12345"), role="partner"))
            db.commit()
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _upload(client, h, data, name="bild.png", mime="image/png"):
    return client.put("/api/me/avatar", headers=h, json={"image": base64.b64encode(data).decode()})


def test_profile_defaults_and_update(client):
    h = _auth(client, "pr_a", full_name="Anna Beispiel")
    p = client.get("/api/me/profile", headers=h).json()
    assert p["display_name"] == "Anna Beispiel" and p["avatar_color"] is None and p["avatar_url"] is None
    r = client.patch("/api/me/profile", headers=h, json={"display_name": "  Anni ", "avatar_color": "#8b5cf6"})
    assert r.status_code == 200
    assert r.json()["display_name"] == "Anni" and r.json()["avatar_color"] == "#8B5CF6"
    me = client.get("/api/auth/me", headers=h).json()
    assert me["display_name"] == "Anni" and me["avatar_color"] == "#8B5CF6"
    # leerer Name → zurück auf den vollen Namen
    assert client.patch("/api/me/profile", headers=h, json={"display_name": ""}).json()["display_name"] == "Anna Beispiel"


@pytest.mark.parametrize("body", [
    {"display_name": "x" * 41},
    {"avatar_color": "red"},
    {"avatar_color": "#12345G"},
    {"avatar_color": "url(javascript:alert(1))"},
])
def test_profile_rejects_invalid(client, body):
    h = _auth(client, "pr_b")
    assert client.patch("/api/me/profile", headers=h, json=body).status_code == 422


@pytest.mark.parametrize("data,mime", [(PNG, "image/png"), (JPEG, "image/jpeg"), (WEBP, "image/webp")])
def test_avatar_upload_and_fetch(client, data, mime):
    h = _auth(client, f"pr_c_{mime.split('/')[1]}")
    r = _upload(client, h, data, mime=mime)
    assert r.status_code == 200, r.text
    url = r.json()["avatar_url"]
    assert url.startswith("/api/users/") and "/avatar?v=" in url
    other = _auth(client, "pr_viewer")
    img = client.get(url, headers=other)  # andere Familienmitglieder dürfen es sehen
    assert img.status_code == 200 and img.content == data
    assert img.headers["content-type"] == mime
    assert img.headers["x-content-type-options"] == "nosniff"
    assert "private" in img.headers["cache-control"]
    assert client.get(url).status_code == 401  # ohne Anmeldung nicht


@pytest.mark.parametrize("data,mime", [
    (b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", "image/svg+xml"),
    (b"<html><script>alert(1)</script></html>", "image/png"),  # falscher Typ, Inhalt zählt
    (b"GIF89a" + b"\x00" * 20, "image/gif"),
    (b"\x89PNG\r\n\x1a\n" + b"\x00" * (600 * 1024), "image/png"),  # zu groß
    (b"", "image/png"),
])
def test_avatar_rejects_non_images_and_large_files(client, data, mime):
    h = _auth(client, "pr_d")
    assert _upload(client, h, data, mime=mime).status_code in (413, 422)


def test_avatar_version_changes_and_delete(client):
    h = _auth(client, "pr_e")
    v1 = _upload(client, h, PNG).json()["avatar_url"]
    v2 = _upload(client, h, JPEG, mime="image/jpeg").json()["avatar_url"]
    assert v1 != v2  # neue Version → Clients laden neu
    assert client.delete("/api/me/avatar", headers=h).json()["avatar_url"] is None
    assert client.get(v2, headers=h).status_code == 404
    v3 = _upload(client, h, PNG).json()["avatar_url"]
    assert v3 not in (v1, v2)  # nach Löschen nie eine alte Version wiederverwenden


def test_people_include_profile(client):
    h = _auth(client, "pr_f", full_name="Fritz")
    client.patch("/api/me/profile", headers=h, json={"display_name": "Fritzi", "avatar_color": "#22B8CF"})
    _upload(client, h, PNG)
    people = {p["username"]: p for p in client.get("/api/auth/people", headers=h).json()}
    f = people["pr_f"]
    assert f["display_name"] == "Fritzi" and f["avatar_color"] == "#22B8CF" and f["avatar_url"].startswith("/api/users/")
    assert "email" not in f


def test_avatar_rejects_invalid_base64(client):
    h = _auth(client, "pr_g")
    assert client.put("/api/me/avatar", headers=h, json={"image": "kein base64 !!"}).status_code == 422
    assert client.put("/api/me/avatar", headers=h, json={"image": ""}).status_code == 422
