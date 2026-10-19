"""Backup and restore (Administration → Backup)."""

import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.config import settings
from app.core.crypto import encrypt
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.config import ConfigOverride
from app.models.user import User
from app.services import backup as svc


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "backup_auto", False)
    monkeypatch.setattr(settings, "backup_keep", 7)
    yield tmp_path
    with SessionLocal() as db:  # settings saved through the API must not leak into the next test
        db.query(ConfigOverride).filter(ConfigOverride.key.like("BACKUP_%")).delete(synchronize_session=False)
        db.commit()


def _user(client, name, role="partner"):
    with SessionLocal() as db:
        if not db.query(User).filter(User.username == name).first():
            db.add(User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"),
                        role=role, is_admin=role == "admin"))
            db.commit()
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _rows(archive: Path, table: str):
    with zipfile.ZipFile(archive) as zf:
        return [json.loads(line) for line in zf.read(f"db/{table}.jsonl").splitlines()]


def _zip(path: Path, manifest: dict, extra: dict = None):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        for name, data in (extra or {}).items():
            zf.writestr(name, data)


def _manifest(**kw):
    base = {"format": 1, "hub_version": "0.1.0", "alembic_revision": svc.current_revision(),
            "created_at": datetime.now(timezone.utc).isoformat(), "tables": {}, "files": []}
    base.update(kw)
    return base


def test_only_admins(client, auth):
    h = _user(client, "bk_partner")
    for method, path in (("get", "/api/admin/backup"), ("post", "/api/admin/backup"),
                         ("post", "/api/admin/backup/download-link")):
        assert getattr(client, method)(path, headers=h).status_code == 403, path
        assert getattr(client, method)(path).status_code == 401, path
    assert client.post("/api/admin/backup/x.zip/restore", headers=h, json={"confirm": True}).status_code == 403


def test_create_backup_keeps_secrets_encrypted(client, auth, data_dir):
    secret = encrypt("hunter2-token")
    with SessionLocal() as db:
        db.merge(ConfigOverride(key="BK_TEST_TOKEN", value=secret, secret=True))
        db.commit()
    r = client.post("/api/admin/backup", headers=auth, json={}).json()
    assert r["ok"] and r["kind"] == "manual"
    archive = data_dir / "backups" / r["name"]
    with zipfile.ZipFile(archive) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert b"hunter2-token" not in b"".join(zf.read(n) for n in zf.namelist())
    assert manifest["format"] == 1 and manifest["alembic_revision"] == svc.current_revision()
    assert any(row["key"] == "BK_TEST_TOKEN" and row["value"] == secret for row in _rows(archive, "config_overrides"))
    overview = client.get("/api/admin/backup", headers=auth).json()
    assert overview["last"]["ok"] is True and overview["last"]["name"] == r["name"]
    assert overview["backups"][0]["name"] == r["name"] and overview["dialect"] == "sqlite"
    assert client.get("/api/admin/overview", headers=auth).json()["backup"]["last_at"] == overview["last"]["at"]


def test_round_trip_restores_data_and_files(client, auth, data_dir, monkeypatch):
    (data_dir / "secret_key").write_text("old-key")
    (data_dir / "vapid.json").write_text('{"private": "p", "public": "q"}')
    monkeypatch.delenv("SECRET_KEY", raising=False)
    _user(client, "bk_keeper")
    name = client.post("/api/admin/backup", headers=auth, json={"include_keys": True}).json()["name"]
    with zipfile.ZipFile(data_dir / "backups" / name) as zf:
        assert {"files/secret_key", "files/vapid.json"} <= set(zf.namelist())

    with SessionLocal() as db:
        db.query(User).filter(User.username == "bk_keeper").delete()
        db.commit()
    (data_dir / "secret_key").write_text("changed-key")

    r = client.post(f"/api/admin/backup/{name}/restore", headers=auth, json={"confirm": True}).json()
    assert r["ok"] and r["restart_required"] is True and r["safety_backup"].startswith("familienhub-prerestore-")
    with SessionLocal() as db:
        assert db.query(User).filter(User.username == "bk_keeper").count() == 1
    assert (data_dir / "secret_key").read_text() == "old-key"
    assert (data_dir / "secret_key.before-restore").read_text() == "changed-key"
    assert oct((data_dir / "secret_key").stat().st_mode & 0o777) == "0o600"
    assert (data_dir / "backups" / r["safety_backup"]).is_file()
    assert client.get("/api/admin/backup", headers=auth).json()["last_restore_at"]


def test_explicit_secret_key_env_is_not_overwritten(client, auth, data_dir, monkeypatch):
    (data_dir / "secret_key").write_text("file-key")
    monkeypatch.setenv("SECRET_KEY", "explicit-key-from-env")
    name = client.post("/api/admin/backup", headers=auth, json={}).json()["name"]
    (data_dir / "secret_key").write_text("other")
    r = client.post(f"/api/admin/backup/{name}/restore", headers=auth, json={"confirm": True}).json()
    assert r["ok"] and r["warnings"] == ["secret_key_env"]
    assert (data_dir / "secret_key").read_text() == "other"


def test_backup_without_keys(client, auth, data_dir):
    (data_dir / "secret_key").write_text("k")
    name = client.post("/api/admin/backup", headers=auth, json={"include_keys": False}).json()["name"]
    with zipfile.ZipFile(data_dir / "backups" / name) as zf:
        assert not any(n.startswith("files/") for n in zf.namelist())


def test_restore_needs_confirmation(client, auth):
    name = client.post("/api/admin/backup", headers=auth, json={}).json()["name"]
    assert client.post(f"/api/admin/backup/{name}/restore", headers=auth, json={}).status_code == 422


def test_newer_backup_is_refused(client, auth, data_dir):
    base = data_dir / "backups"
    base.mkdir()
    _zip(base / "familienhub-uploaded-1.zip", _manifest(hub_version="99.0.0"))
    r = client.post("/api/admin/backup/familienhub-uploaded-1.zip/inspect", headers=auth).json()
    assert r["ok"] is False and r["code"] == "newer_version"
    r = client.post("/api/admin/backup/familienhub-uploaded-1.zip/restore", headers=auth, json={"confirm": True}).json()
    assert r["ok"] is False and r["code"] == "newer_version"


def test_unknown_and_older_schema_are_refused(client, auth, data_dir):
    base = data_dir / "backups"
    base.mkdir()
    _zip(base / "a.zip", _manifest(alembic_revision="ffffffffffff"))
    assert client.post("/api/admin/backup/a.zip/inspect", headers=auth).json()["code"] == "newer_version"
    old = svc.known_revisions() - {svc.current_revision()}
    _zip(base / "b.zip", _manifest(alembic_revision=sorted(old)[0]))
    assert client.post("/api/admin/backup/b.zip/inspect", headers=auth).json()["code"] == "older_schema"


def test_malicious_or_broken_archives_are_refused(client, auth, data_dir):
    base = data_dir / "backups"
    base.mkdir()
    _zip(base / "slip.zip", _manifest(), {"../../evil": "x"})
    _zip(base / "abs.zip", _manifest(), {"files/other": "x"})
    (base / "text.zip").write_text("not a zip")
    _zip(base / "nomanifest.zip", _manifest())
    with zipfile.ZipFile(base / "nomanifest.zip", "w") as zf:
        zf.writestr("db/users.jsonl", "")
    for name, code in (("slip.zip", "unsafe"), ("abs.zip", "unsafe"), ("text.zip", "not_a_backup"),
                       ("nomanifest.zip", "not_a_backup")):
        r = client.post(f"/api/admin/backup/{name}/inspect", headers=auth).json()
        assert (r["ok"], r["code"]) == (False, code), name
    # names cannot leave the backup folder
    assert client.post("/api/admin/backup/..%2Fsecret_key/inspect", headers=auth).json().get("ok") is not True
    assert client.post("/api/admin/backup/x.txt/inspect", headers=auth).json()["code"] == "bad_name"


def test_failed_restore_leaves_database_unchanged(client, auth, data_dir):
    _user(client, "bk_stays")
    base = data_dir / "backups"
    base.mkdir()
    _zip(base / "broken.zip", _manifest(tables={"users": 1}), {"db/users.jsonl": "{not json\n"})
    r = client.post("/api/admin/backup/broken.zip/restore", headers=auth, json={"confirm": True}).json()
    assert r["ok"] is False
    with SessionLocal() as db:
        assert db.query(User).filter(User.username == "bk_stays").count() == 1


def test_upload_then_inspect(client, auth, data_dir):
    name = client.post("/api/admin/backup", headers=auth, json={}).json()["name"]
    blob = (data_dir / "backups" / name).read_bytes()
    r = client.post("/api/admin/backup/upload", headers={**auth, "Content-Type": "application/octet-stream"},
                    content=blob).json()
    assert r["ok"] and r["name"].startswith("familienhub-uploaded-")
    assert r["manifest"]["hub_version"] == svc.__version__
    bad = client.post("/api/admin/backup/upload", headers={**auth, "Content-Type": "application/octet-stream"},
                      content=b"nope").json()
    assert bad["ok"] is False and bad["code"] == "not_a_backup"
    assert not list((data_dir / "backups").glob(".upload-*"))


def test_download_link_is_single_use_and_admin_bound(client, auth):
    link = client.post("/api/admin/backup/download-link", headers=auth, json={}).json()["path"]
    r = client.get(link)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert json.loads(zf.read("manifest.json"))["hub_version"] == svc.__version__
    assert client.get(link).status_code == 401  # used
    assert client.get("/api/admin/backup/download?token=garbage").status_code == 401
    assert client.get("/api/admin/backup", headers=auth).json()["last"]["kind"] == "download"


def test_delete_stored_backup(client, auth, data_dir):
    name = client.post("/api/admin/backup", headers=auth, json={}).json()["name"]
    assert client.delete(f"/api/admin/backup/{name}", headers=auth).json() == {"ok": True}
    assert not (data_dir / "backups" / name).exists()
    assert client.delete(f"/api/admin/backup/{name}", headers=auth).json()["code"] == "not_found"


def test_settings_and_retention(client, auth, data_dir):
    r = client.put("/api/admin/backup/settings", headers=auth, json={"auto": True, "keep": 2}).json()
    assert r["auto"] is True and r["keep"] == 2
    assert client.put("/api/admin/backup/settings", headers=auth, json={"auto": True, "keep": 0}).status_code == 422
    base = data_dir / "backups"
    base.mkdir(exist_ok=True)
    for day in range(1, 5):  # older automatic backups
        _zip(base / f"familienhub-auto-2026010{day}-030000.zip", _manifest(created_at=f"2026-01-0{day}T03:00:00+00:00"))
    assert svc.create_backup("auto")["ok"]
    autos = sorted(p.name for p in base.glob("familienhub-auto-*.zip"))
    assert len(autos) == 2 and autos[0] == "familienhub-auto-20260104-030000.zip"
    client.put("/api/admin/backup/settings", headers=auth, json={"auto": False, "keep": 7})


def test_auto_is_due_once_per_day_after_0330(monkeypatch):
    monkeypatch.setattr(settings, "timezone", "UTC")
    day = lambda h, m: datetime(2026, 5, 4, h, m, tzinfo=timezone.utc)  # noqa: E731
    assert svc.auto_due(day(4, 0)) is False  # switched off
    monkeypatch.setattr(settings, "backup_auto", "true")  # overrides arrive as text
    assert svc.auto_due(day(3, 29)) is False
    assert svc.auto_due(day(3, 30)) is True
    assert svc.create_backup("auto")["ok"]
    today = datetime.now(timezone.utc).replace(hour=23, minute=0)
    assert svc.auto_due(today) is False


def test_failure_is_soft(client, auth, data_dir, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("disk exploded")

    monkeypatch.setattr(svc, "create_archive", boom)
    r = client.post("/api/admin/backup", headers=auth, json={}).json()
    assert r["ok"] is False and r["code"] == "failed"
    assert "exploded" not in json.dumps(r)
    overview = client.get("/api/admin/backup", headers=auth).json()
    assert overview["last"]["error"] == "failed"


def test_unwritable_data_dir_is_soft(client, auth, data_dir, monkeypatch):
    blocker = data_dir / "file"
    blocker.write_text("x")
    monkeypatch.setattr(settings, "data_dir", str(blocker))  # backups/ cannot be created below a file
    r = client.post("/api/admin/backup", headers=auth, json={}).json()
    assert r["ok"] is False and r["code"] == "dir_not_writable"
    assert client.get("/api/admin/backup", headers=auth).status_code == 200


def test_version_ordering():
    v = svc.parse_version
    assert v("1.0.0-beta.1") < v("1.0.0-beta.2") < v("1.0.0-beta.10") < v("1.0.0") < v("1.0.1") < v("v1.1.0")
    assert v("dev") is None and svc.is_prerelease("1.0.0-beta.1") and not svc.is_prerelease("1.0.0")
