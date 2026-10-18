"""SECRET_KEY: explicit value wins; otherwise generated once into <DATA_DIR>/secret_key (0600) and reused."""

import stat

from app.config import PLACEHOLDER_SECRET_KEY, Settings


def _settings(tmp_path, **kw):
    return Settings(_env_file=None, data_dir=str(tmp_path / "data"), **kw)


def test_generated_once_with_0600_and_reused(tmp_path):
    first = _settings(tmp_path, secret_key="")
    path = tmp_path / "data" / "secret_key"
    assert path.exists()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert len(first.secret_key) >= 48 and first.secret_key != PLACEHOLDER_SECRET_KEY
    assert path.read_text().strip() == first.secret_key
    second = _settings(tmp_path, secret_key="")
    assert second.secret_key == first.secret_key


def test_placeholder_is_replaced_too(tmp_path):
    s = _settings(tmp_path, secret_key=PLACEHOLDER_SECRET_KEY)
    assert s.secret_key != PLACEHOLDER_SECRET_KEY and (tmp_path / "data" / "secret_key").exists()


def test_explicit_secret_key_wins(tmp_path):
    s = _settings(tmp_path, secret_key="x" * 40)
    assert s.secret_key == "x" * 40
    assert not (tmp_path / "data").exists()


def test_existing_file_is_not_overwritten(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "secret_key").write_text("stored-key-value\n")
    assert _settings(tmp_path, secret_key="").secret_key == "stored-key-value"


def test_unwritable_data_dir_falls_back(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    s = Settings(_env_file=None, data_dir=str(blocker / "sub"), secret_key="")
    assert s.secret_key == PLACEHOLDER_SECRET_KEY  # old behaviour; startup check rejects it in production
