"""App-Sitzung: Refresh-Token im Body, Kalender pro Nutzer, ISO-Wochen (Nachträge zu WP 6)."""

from datetime import datetime

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.caldav import CalDAVAccount
from app.models.user import User


def _local_now():
    """Jetzt in Ortszeit (TIMEZONE), naiv – wie „Heute“ rechnet. date.today() wäre im Container UTC."""
    from app.core.timeutil import local_tz

    return datetime.now(local_tz()).replace(tzinfo=None)


def _ensure_user(username: str) -> User:
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            user = User(
                username=username,
                email=f"{username}@test.de",
                hashed_password=get_password_hash("pw-12345"),
                role="partner",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user


def _login(client, username: str, client_kind: str = "app") -> dict:
    resp = client.post(
        "/api/auth/login",
        json={"username": username, "password": "pw-12345", "client": client_kind},
    )
    assert resp.status_code == 200
    return resp.json()


def test_login_as_app_returns_refresh_token_web_does_not(client):
    _ensure_user("app_user1")
    assert _login(client, "app_user1", "app")["refresh_token"]
    assert _login(client, "app_user1", "web")["refresh_token"] is None


def test_refresh_with_body_token_rotates(client):
    _ensure_user("app_user2")
    old = _login(client, "app_user2")["refresh_token"]
    client.cookies.clear()  # wie die native App: keine Cookies

    resp = client.post("/api/auth/refresh", json={"refresh_token": old})
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"] and body["refresh_token"] != old

    # Das alte Token ist widerrufen, das neue gilt
    assert client.post("/api/auth/refresh", json={"refresh_token": old}).status_code == 401
    assert client.post("/api/auth/refresh", json={"refresh_token": body["refresh_token"]}).status_code == 200


def test_refresh_without_token_401(client):
    client.cookies.clear()
    assert client.post("/api/auth/refresh").status_code == 401


def _add_account(username: str, url: str, user_name: str, password: str) -> User:
    from app.core.crypto import encrypt

    user = _ensure_user(username)
    with SessionLocal() as db:
        db.query(CalDAVAccount).filter(CalDAVAccount.user_id == user.id).delete()
        db.add(CalDAVAccount(user_id=user.id, url=url, username=user_name, password_enc=encrypt(password)))
        db.commit()
    return user


def _bearer(client, username: str) -> dict:
    return {"Authorization": f"Bearer {_login(client, username)['access_token']}"}


def test_events_use_user_account_credentials(client, monkeypatch):
    from app.connectors import caldav_connector

    _add_account("cal_user1", "https://dav.example.test/u1", "u1", "geheim-u1")
    seen = {}

    def fake_fetch(self, start, end):
        seen.update(url=self.url, username=self.username, password=self.password)
        return [{"title": "Elternabend", "start": "2026-10-14T19:00:00", "end": None,
                 "all_day": False, "calendar": "Privat"}]

    monkeypatch.setattr(caldav_connector.CalDAVConnector, "_fetch_events_sync", fake_fetch)
    resp = client.get("/api/calendar/events?days=7", headers=_bearer(client, "cal_user1"))
    assert resp.status_code == 200
    assert resp.json()[0]["title"] == "Elternabend"
    assert seen == {"url": "https://dav.example.test/u1", "username": "u1", "password": "geheim-u1"}


def test_create_event_does_not_touch_global_settings(client, monkeypatch):
    from app.config import settings
    from app.connectors import caldav_connector

    _add_account("cal_user2", "https://dav.example.test/u2", "u2", "geheim-u2")
    before = (settings.caldav_url, settings.caldav_username, settings.caldav_password)
    seen = {}

    def fake_create(self, title, start, end, all_day, calendar_url=None):
        seen.update(url=self.url, username=self.username, global_url=settings.caldav_url)
        return {"uid": "x1", "title": title, "start": start, "end": end, "all_day": all_day}

    monkeypatch.setattr(caldav_connector.CalDAVConnector, "_create_event_sync", fake_create)
    resp = client.post(
        "/api/calendar/events",
        headers=_bearer(client, "cal_user2"),
        json={"title": "Zahnarzt", "start": "2026-10-20T10:00:00", "end": "2026-10-20T11:00:00", "all_day": False},
    )
    assert resp.status_code == 201
    assert resp.json()["uid"] == "x1"
    assert seen["url"] == "https://dav.example.test/u2" and seen["username"] == "u2"
    assert seen["global_url"] == before[0]  # globale Einstellungen bleiben unberührt
    assert (settings.caldav_url, settings.caldav_username, settings.caldav_password) == before


def test_today_lists_events_from_user_calendar(client, monkeypatch):
    from app.connectors import caldav_connector

    _add_account("cal_user3", "https://dav.example.test/u3", "u3", "geheim-u3")
    calls = {}

    def fake_fetch(self, start, end):
        calls.update(start=start, end=end)
        return [{"title": "Kita-Fest", "start": f"{_local_now().date().isoformat()}T15:00:00",
                 "end": None, "all_day": False, "calendar": "Familie"}]

    monkeypatch.setattr(caldav_connector.CalDAVConnector, "_fetch_events_sync", fake_fetch)
    resp = client.get("/api/today", headers=_bearer(client, "cal_user3"))
    assert resp.status_code == 200
    assert [e["title"] for e in resp.json()["events"]] == ["Kita-Fest"]
    # Zeitraum: ab heute 00:00, zwei Tage
    assert calls["start"] == datetime.combine(_local_now().date(), datetime.min.time())
    assert (calls["end"] - calls["start"]).days == 2


def test_meals_week_uses_iso_weeks(client, auth):
    # 2026-W01 beginnt nach ISO am Montag, 29.12.2025 (mit %W wäre es der 05.01.2026)
    resp = client.get("/api/meals?week=2026-W01", headers=auth)
    assert resp.status_code == 200
    days = [d["date"] for d in resp.json()["days"]]
    assert days[0] == "2025-12-29"
    assert days[-1] == "2026-01-04"
    assert len(days) == 7


def test_people_lists_active_users_without_private_fields(client):
    _ensure_user("people_a")
    with SessionLocal() as db:
        inactive = db.query(User).filter(User.username == "people_off").first()
        if not inactive:
            db.add(User(username="people_off", email="off@test.de",
                        hashed_password=get_password_hash("x"), role="partner", is_active=False))
            db.commit()
    resp = client.get("/api/auth/people", headers=_bearer(client, "people_a"))
    assert resp.status_code == 200
    people = {p["username"]: p for p in resp.json()}
    assert "people_a" in people and "people_off" not in people
    # Profilfelder (Anzeigename, Farbe, Bild) sind öffentlich in der Familie; E-Mail und Rolle nicht
    assert set(people["people_a"]) == {"id", "username", "display_name", "avatar_color", "avatar_url"}
    assert "email" not in people["people_a"] and "role" not in people["people_a"]


def test_health_reports_oidc_flag(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "oidc_issuer", "")
    assert client.get("/api/health").json()["features"]["oidc"] is False
    monkeypatch.setattr(settings, "oidc_issuer", "https://idp.example.test/app/")
    monkeypatch.setattr(settings, "oidc_client_id", "hub")
    assert client.get("/api/health").json()["features"]["oidc"] is True



def test_redact_db_url_hides_password():
    from app.core.database import redact_db_url

    out = redact_db_url("postgresql+psycopg2://hub:geheim-123@db:5432/hub")
    assert "geheim-123" not in out
    assert out == "postgresql+psycopg2://hub:***@db:5432/hub"


def test_startup_log_does_not_contain_database_password(monkeypatch, caplog):
    """Der echte App-Start (lifespan) darf das DB-Passwort nicht loggen."""
    import logging

    from fastapi.testclient import TestClient

    import app.main as main_module
    from app.config import settings

    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg2://hub:geheim-123@db:5432/hub")
    monkeypatch.setattr(main_module, "init_db", lambda: None)
    with caplog.at_level(logging.INFO):
        with TestClient(main_module.app):
            pass
    assert "Database initialized: postgresql+psycopg2://hub:***@db:5432/hub" in caplog.text
    assert "geheim-123" not in caplog.text
