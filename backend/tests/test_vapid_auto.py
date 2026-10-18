"""Web Push keys are generated once into DATA_DIR when none are configured."""

import base64
import json
import os
import stat

from app.config import Settings


def _settings(tmp_path, **kw):
    return Settings(_env_file=None, data_dir=str(tmp_path / "data"), vapid_auto=True, **kw)


def _raw(b64: str) -> bytes:
    return base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4))


def test_keys_generated_once_and_reused(tmp_path):
    first = _settings(tmp_path)
    assert len(_raw(first.vapid_private_key)) == 32
    assert len(_raw(first.vapid_public_key)) == 65 and _raw(first.vapid_public_key)[0] == 4  # uncompressed P-256
    path = tmp_path / "data" / "vapid.json"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    second = _settings(tmp_path)
    assert (second.vapid_private_key, second.vapid_public_key) == (first.vapid_private_key, first.vapid_public_key)
    assert json.loads(path.read_text())["public"] == first.vapid_public_key


def test_configured_keys_win_and_nothing_is_written(tmp_path):
    s = _settings(tmp_path, vapid_private_key="PRIV", vapid_public_key="PUB")
    assert (s.vapid_private_key, s.vapid_public_key) == ("PRIV", "PUB")
    assert not (tmp_path / "data" / "vapid.json").exists()


def test_auto_off_keeps_web_push_unconfigured(tmp_path):
    s = Settings(_env_file=None, data_dir=str(tmp_path / "data"), vapid_auto=False)
    assert s.vapid_private_key is None and s.vapid_public_key is None


def test_unusable_data_dir_fails_softly(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    s = Settings(_env_file=None, data_dir=str(blocker / "sub"), vapid_auto=True)
    assert s.vapid_private_key is None


def test_push_contact_is_admin_email_unless_configured(client, auth, monkeypatch):
    from app.config import settings
    from app.core.database import SessionLocal
    from app.models.user import ROLE_ADMIN, User
    from app.services.notify import vapid_contact

    db = SessionLocal()
    admin = db.query(User).filter(User.role == ROLE_ADMIN, User.is_active == True).order_by(User.id).first()  # noqa: E712
    assert admin is not None
    monkeypatch.setattr(settings, "vapid_email", "")
    assert vapid_contact(db) == f"mailto:{admin.email}"
    monkeypatch.setattr(settings, "vapid_email", "mailto:admin@example.org")  # placeholder from old .env files
    assert vapid_contact(db) == f"mailto:{admin.email}"
    monkeypatch.setattr(settings, "vapid_email", "push@family.test")
    assert vapid_contact(db) == "mailto:push@family.test"
    db.close()
