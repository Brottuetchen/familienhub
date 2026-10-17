"""Erinnerungen: privat vs. Familie, Versand an die richtigen Personen."""

import asyncio
from datetime import datetime, timedelta

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.reminder import Reminder
from app.models.user import User


def _local_now():
    """Jetzt in Ortszeit (TIMEZONE), naiv – wie „Heute“ rechnet. date.today() wäre im Container UTC."""
    from app.core.timeutil import local_tz

    return datetime.now(local_tz()).replace(tzinfo=None)


def _user(name: str) -> User:
    with SessionLocal() as db:
        u = db.query(User).filter(User.username == name).first()
        if not u:
            u = User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"), role="partner")
            db.add(u)
            db.commit()
            db.refresh(u)
        return u


def _auth(client, name: str) -> dict:
    _user(name)
    token = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_private_reminder_only_for_creator_family_for_all(client):
    a, b = _auth(client, "rem_a"), _auth(client, "rem_b")
    private = client.post("/api/reminders", headers=a, json={"title": "Geschenk für B besorgen"}).json()
    family = client.post("/api/reminders", headers=a, json={"title": "Müll raus", "for_family": True}).json()
    assert private["for_family"] is False and family["for_family"] is True

    titles_a = {r["title"] for r in client.get("/api/reminders", headers=a).json()}
    titles_b = {r["title"] for r in client.get("/api/reminders", headers=b).json()}
    assert {"Geschenk für B besorgen", "Müll raus"} <= titles_a
    assert "Müll raus" in titles_b
    assert "Geschenk für B besorgen" not in titles_b

    # Fremde private Erinnerung: weder ändern noch löschen
    assert client.patch(f"/api/reminders/{private['id']}", headers=b, json={"completed": True}).status_code == 404
    assert client.delete(f"/api/reminders/{private['id']}", headers=b).status_code == 404
    assert client.patch(f"/api/reminders/{family['id']}", headers=b, json={"completed": True}).status_code == 200


def test_today_shows_only_visible_reminders(client):
    a, b = _auth(client, "rem_c"), _auth(client, "rem_d")
    soon = (_local_now().replace(hour=23, minute=0, second=0, microsecond=0)).isoformat()
    client.post("/api/reminders", headers=a, json={"title": "Privat heute C", "due_at": soon})
    titles_b = [r["title"] for r in client.get("/api/today", headers=b).json()["reminders"]]
    titles_a = [r["title"] for r in client.get("/api/today", headers=a).json()["reminders"]]
    assert "Privat heute C" in titles_a
    assert "Privat heute C" not in titles_b


def test_scheduler_notifies_creator_or_whole_family(monkeypatch):
    from app.services import scheduler

    a, b = _user("rem_e"), _user("rem_f")
    past = datetime.utcnow() - timedelta(minutes=1)  # direkt in die DB: UTC
    with SessionLocal() as db:
        # andere fällige Erinnerungen aus früheren Tests nicht mitzählen
        db.query(Reminder).filter(Reminder.notified == False).update({"notified": True})  # noqa: E712
        db.add(Reminder(title="nur E", due_at=past, created_by=a.id))
        db.add(Reminder(title="alle", due_at=past, created_by=a.id, for_family=True))
        db.commit()
        active = {u.id for u in db.query(User).filter(User.is_active == True).all()}  # noqa: E712

    sent = []

    async def fake_notify(user_id, title, body, data=None, category="info"):
        sent.append((user_id, body, category, data.get("route")))
        return 1

    monkeypatch.setattr(scheduler, "notify", fake_notify)
    asyncio.run(scheduler._tick())

    only_e = [s for s in sent if s[1] == "nur E"]
    to_all = [s for s in sent if s[1] == "alle"]
    assert [s[0] for s in only_e] == [a.id]
    assert {s[0] for s in to_all} == active and b.id in active
    assert all(s[2] == "reminder" and s[3] == "/reminders" for s in sent)
    with SessionLocal() as db:
        assert db.query(Reminder).filter(Reminder.title.in_(["nur E", "alle"]), Reminder.notified == True).count() == 2  # noqa: E712
