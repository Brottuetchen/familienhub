"""Tests für die Alembic-Migrationen (Schema-Treue + Bestandsschutz)."""

from alembic import command
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app import models  # noqa: F401  (registriert alle Tabellen)
from app.config import settings
from app.core.database import Base, _alembic_config
from app.core.security import get_password_hash
from app.models.user import User


def _schema(engine):
    insp = inspect(engine)
    return {
        t: sorted(c["name"] for c in insp.get_columns(t))
        for t in insp.get_table_names()
        if t != "alembic_version"
    }


def test_alembic_head_matches_models(tmp_path, monkeypatch):
    # 'create_all' (Modell-Wahrheit) muss identisch zu 'upgrade head' sein.
    ref = create_engine(f"sqlite:///{tmp_path}/ref.db")
    Base.metadata.create_all(ref)
    ref_schema = _schema(ref)

    mig_url = f"sqlite:///{tmp_path}/mig.db"
    monkeypatch.setattr(settings, "database_url", mig_url)
    command.upgrade(_alembic_config(), "head")
    mig_schema = _schema(create_engine(mig_url))

    assert mig_schema == ref_schema
    assert "users" in mig_schema  # sanity


def test_stamp_preserves_existing_data(tmp_path, monkeypatch):
    # Alt-Installation: via create_all entstanden, mit Daten, OHNE alembic_version.
    from app.models.config import ConfigOverride

    url = f"sqlite:///{tmp_path}/existing.db"
    eng = create_engine(url)
    Base.metadata.create_all(eng)
    # Alt-Stand simulieren: die NEUESTE Tabelle gab es damals noch nicht.
    ConfigOverride.__table__.drop(eng)
    with Session(eng) as s:
        s.add(User(username="old", email="o@e.de", hashed_password=get_password_hash("x"),
                   role="admin", is_admin=True))
        s.commit()
    eng.dispose()

    monkeypatch.setattr(settings, "database_url", url)
    cfg = _alembic_config()
    insp = inspect(create_engine(url))
    assert insp.has_table("users") and not insp.has_table("alembic_version")
    assert not insp.has_table("config_overrides")

    # Bestandsschutz-Pfad (spiegelt init_db): Baseline stampen, dann upgrade head.
    base = ScriptDirectory.from_config(cfg).get_bases()[0]
    command.stamp(cfg, base)
    command.upgrade(cfg, "head")

    eng2 = create_engine(url)
    with eng2.connect() as conn:
        from sqlalchemy import text
        assert conn.execute(text("SELECT COUNT(*) FROM users WHERE username='old'")).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM alembic_version")).scalar() == 1
    # die neue Migration hat die fehlende Tabelle ergänzt (kein Datenverlust)
    assert inspect(eng2).has_table("config_overrides")


def test_migrations_do_not_commit_themselves():
    """Ein eigenes commit() in einer Migration beendet auf Postgres die Alembic-Transaktion.

    Folge im Betrieb (14.10.): Versionsstand blieb stehen, oidc_sessions fehlte. SQLite merkt das nicht.
    """
    import pathlib
    import re

    versions = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
    offenders = [p.name for p in versions.glob("*.py") if re.search(r"\.commit\(\)", p.read_text())]
    assert offenders == []


@pytest.mark.parametrize("stamp_revision", [None, "a7b8c9d0e1f2"], ids=["baseline", "previous_revision"])
def test_legacy_create_all_stamp_upgrade_preserves_users_and_caldav(
    tmp_path, monkeypatch, stamp_revision
):
    from app.core.crypto import encrypt
    from app.models.caldav import CalDAVAccount

    url = f"sqlite:///{tmp_path}/legacy-create-all.db"
    monkeypatch.setattr(settings, "database_url", url)
    engine = create_engine(url)
    habitica_tables = {"habitica_accounts", "habitica_selections", "habitica_operations"}
    if stamp_revision is None:
        initial_tables = {
            "login_attempts",
            "meal_plan",
            "recipes",
            "refresh_tokens",
            "reminders",
            "users",
        }
        legacy_tables = [Base.metadata.tables[name] for name in initial_tables]
    else:
        legacy_tables = [
            table for name, table in Base.metadata.tables.items() if name not in habitica_tables
        ]
    Base.metadata.create_all(engine, tables=legacy_tables)
    if stamp_revision is None:
        CalDAVAccount.__table__.create(engine)

    user_password = get_password_hash("legacy-user-password")
    caldav_password = encrypt("legacy-caldav-password")
    with Session(engine) as db:
        user = User(
            username="legacy",
            email="legacy@example.test",
            hashed_password=user_password,
            role="admin",
            is_admin=True,
        )
        db.add(user)
        db.flush()
        db.add(
            CalDAVAccount(
                user_id=user.id,
                url="https://cloud.example",
                username="legacy-caldav",
                password_enc=caldav_password,
            )
        )
        db.commit()
        user_id = user.id

    before = inspect(engine)
    assert not before.has_table("alembic_version")
    assert all(not before.has_table(name) for name in habitica_tables)

    cfg = _alembic_config()
    revision = stamp_revision or ScriptDirectory.from_config(cfg).get_bases()[0]
    command.stamp(cfg, revision)
    command.upgrade(cfg, "head")

    after = inspect(engine)
    assert all(after.has_table(name) for name in habitica_tables)
    with Session(engine) as db:
        persisted_user = db.get(User, user_id)
        persisted_caldav = db.query(CalDAVAccount).one()
        assert persisted_user.hashed_password == user_password
        assert persisted_caldav.password_enc == caldav_password


def test_habitica_upgrade_downgrade_keeps_existing_nextcloud_accounts(tmp_path, monkeypatch):
    from app.core.crypto import encrypt
    from app.models.caldav import CalDAVAccount
    from app.models.habitica import HabiticaAccount, HabiticaSelection, HabiticaOperation

    url = f"sqlite:///{tmp_path}/provider-migration.db"
    monkeypatch.setattr(settings, "database_url", url)
    cfg = _alembic_config()
    command.upgrade(cfg, "a7b8c9d0e1f2")
    engine = create_engine(url)
    # Auf altem Schemastand nur mit dessen Spalten schreiben (das ORM-Modell kennt neuere Spalten).
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (username, email, hashed_password, role, is_active, is_admin, created_at) "
                          "VALUES ('migration', 'migration@example.test', 'test', 'admin', 1, 0, CURRENT_TIMESTAMP)"))
        user_id = conn.execute(text("SELECT id FROM users WHERE username = 'migration'")).scalar_one()
    with Session(engine) as db:
        db.add(CalDAVAccount(user_id=user_id, url="https://cloud.example", username="own", password_enc=encrypt("test")))
        db.commit()
    command.upgrade(cfg, "head")
    with Session(engine) as db:
        assert db.query(CalDAVAccount).one().url == "https://cloud.example"
        db.add(HabiticaAccount(user_id=user_id, server_url="https://habitica.example", remote_user_id="native", api_key_enc=encrypt("test")))
        db.add(HabiticaSelection(user_id=user_id, account_ref="own", remote_id="selected"))
        db.add(HabiticaOperation(key="confirmed", user_id=user_id, account_ref="own", fingerprint="test", state="confirmed", result={}))
        db.commit()
    command.downgrade(cfg, "a7b8c9d0e1f2")
    assert not inspect(engine).has_table("habitica_accounts")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT username FROM users WHERE id = :i"), {"i": user_id}).scalar_one() == "migration"
    with Session(engine) as db:
        assert db.query(CalDAVAccount).one().username == "own"
    command.upgrade(cfg, "head")
    assert all(inspect(engine).has_table(name) for name in ("habitica_accounts", "habitica_selections", "habitica_operations"))
