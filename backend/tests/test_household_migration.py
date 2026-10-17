"""Schema und Rückweg des Abschlussbelegs."""
from alembic import command
from sqlalchemy import create_engine, inspect, text

from app.config import settings
from app.core.database import _alembic_config


def test_household_completion_migration_roundtrip(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/household.db"
    monkeypatch.setattr(settings, "database_url", url)
    cfg = _alembic_config()
    command.upgrade(cfg, "f6a7b8c9d0e1")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (username,email,hashed_password,role,is_active,is_admin) "
                          "VALUES ('before','before@example.com','hash','partner',1,0)"))
    command.upgrade(cfg, "head")
    assert inspect(engine).has_table("task_completions")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO task_completions (uid) VALUES ('one')"))
    command.downgrade(cfg, "f6a7b8c9d0e1")
    assert not inspect(engine).has_table("task_completions")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT username FROM users")).scalar() == "before"
    command.upgrade(cfg, "head")
    assert inspect(engine).has_table("task_completions")
