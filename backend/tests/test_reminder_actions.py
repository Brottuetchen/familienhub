"""Erinnerungen 2.0 (#24/#25): Zeitzonen, Wiederholung über die Zeitumstellung, Knöpfe in Mitteilungen."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.database import SessionLocal
from app.core.security import create_reminder_action_token, get_password_hash
from app.models.reminder import Reminder
from app.models.user import User

BERLIN = ZoneInfo("Europe/Berlin")


def _auth(client, name):
    with SessionLocal() as db:
        u = db.query(User).filter(User.username == name).first()
        if not u:
            u = User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"), role="partner")
            db.add(u)
            db.commit()
            db.refresh(u)
        uid = u.id
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}, uid


def test_due_at_stored_utc_and_returned_with_z(client):
    h, _ = _auth(client, "ra_a")
    r = client.post("/api/reminders", headers=h, json={"title": "Arzt", "due_at": "2026-10-15T09:00:00+02:00"}).json()
    assert r["due_at"] == "2026-10-15T07:00:00Z"
    # ohne Zeitzone = Ortszeit (Europe/Berlin)
    r2 = client.post("/api/reminders", headers=h, json={"title": "Arzt 2", "due_at": "2026-10-15T09:00:00"}).json()
    assert r2["due_at"] == "2026-10-15T07:00:00Z"


def test_weekly_keeps_local_time_across_dst():
    from app.services.recurrence import advance_utc

    # Mi 21.10.2026 09:00 Sommerzeit = 07:00 UTC; nach der Umstellung (25.10.) ist 09:00 = 08:00 UTC
    assert advance_utc(datetime(2026, 10, 21, 7, 0), "weekly") == datetime(2026, 10, 28, 8, 0)
    assert advance_utc(datetime(2026, 10, 24, 7, 0), "daily") == datetime(2026, 10, 25, 8, 0)


def _reminder(client, h, **kw):
    body = {"title": "Müll raus", "due_at": "2026-10-15T09:00:00+02:00", **kw}
    return client.post("/api/reminders", headers=h, json=body).json()


def test_action_done_completes_and_recurring_rolls_forward(client):
    h, uid = _auth(client, "ra_b")
    once = _reminder(client, h)
    r = client.post(f"/api/reminders/{once['id']}/action",
                    json={"action": "done", "token": create_reminder_action_token(once["id"], uid)})
    assert r.status_code == 200 and r.json()["completed"] is True

    weekly = _reminder(client, h, recurrence="weekly")
    r = client.post(f"/api/reminders/{weekly['id']}/action",
                    json={"action": "done", "token": create_reminder_action_token(weekly["id"], uid)}).json()
    assert r["completed"] is False and r["due_at"] == "2026-10-22T07:00:00Z"


def test_action_snooze_and_tomorrow(client):
    h, uid = _auth(client, "ra_c")
    rem = _reminder(client, h)
    tok = create_reminder_action_token(rem["id"], uid)
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    due = client.post(f"/api/reminders/{rem['id']}/action", json={"action": "snooze_1h", "token": tok}).json()["due_at"]
    due = datetime.fromisoformat(due.rstrip("Z"))
    assert timedelta(minutes=59) < due - before < timedelta(minutes=61)

    due = client.post(f"/api/reminders/{rem['id']}/action", json={"action": "tomorrow", "token": tok}).json()["due_at"]
    local = datetime.fromisoformat(due.rstrip("Z")).replace(tzinfo=timezone.utc).astimezone(BERLIN)
    assert (local.hour, local.minute) == (8, 0)
    assert local.date() == (datetime.now(BERLIN) + timedelta(days=1)).date()
    with SessionLocal() as db:
        assert db.get(Reminder, rem["id"]).notified is False


def test_action_token_bound_to_reminder_and_person(client):
    h, uid = _auth(client, "ra_d")
    other_h, other_uid = _auth(client, "ra_e")
    mine = _reminder(client, h)
    second = _reminder(client, h)
    # falsches Token / fremde Erinnerung / unbekannte Aktion
    assert client.post(f"/api/reminders/{mine['id']}/action", json={"action": "done", "token": "x"}).status_code == 401
    tok_second = create_reminder_action_token(second["id"], uid)
    assert client.post(f"/api/reminders/{mine['id']}/action", json={"action": "done", "token": tok_second}).status_code == 401
    # Person ohne Sicht auf die private Erinnerung
    tok_other = create_reminder_action_token(mine["id"], other_uid)
    assert client.post(f"/api/reminders/{mine['id']}/action", json={"action": "done", "token": tok_other}).status_code == 404
    tok = create_reminder_action_token(mine["id"], uid)
    assert client.post(f"/api/reminders/{mine['id']}/action", json={"action": "löschen", "token": tok}).status_code == 400
    # normales Anmelde-Token zählt nicht als Aktions-Token
    login = h["Authorization"].split()[1]
    assert client.post(f"/api/reminders/{mine['id']}/action", json={"action": "done", "token": login}).status_code == 401


def test_snooze_endpoint_requires_login_and_visibility(client):
    h, _ = _auth(client, "ra_f")
    other_h, _ = _auth(client, "ra_g")
    rem = _reminder(client, h)
    assert client.post(f"/api/reminders/{rem['id']}/snooze", json={"minutes": 30}).status_code == 401
    assert client.post(f"/api/reminders/{rem['id']}/snooze", headers=other_h, json={"minutes": 30}).status_code == 404
    assert client.post(f"/api/reminders/{rem['id']}/snooze", headers=h, json={"minutes": 1}).status_code == 422
    assert client.post(f"/api/reminders/{rem['id']}/snooze", headers=h, json={"minutes": 30}).status_code == 200


def test_scheduler_sends_action_token(monkeypatch):
    import asyncio

    from app.core.security import verify_reminder_action_token
    from app.services import scheduler

    with SessionLocal() as db:
        db.query(Reminder).filter(Reminder.notified == False).update({"notified": True})  # noqa: E712
        u = db.query(User).filter(User.username == "admin").first() or db.query(User).first()
        r = Reminder(title="Pille", due_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1),
                     created_by=u.id)
        db.add(r)
        db.commit()
        rid, uid = r.id, u.id
    sent = []

    async def fake_notify(user_id, title, body, data=None, category="info", **kw):
        sent.append(data)
        return 1

    monkeypatch.setattr(scheduler, "notify", fake_notify)
    asyncio.run(scheduler._tick())
    data = next(d for d in sent if d.get("reminder_id") == rid)
    assert data["actions"] == "done,snooze_1h,tomorrow"
    claims = verify_reminder_action_token(data["action_token"])
    assert claims["rid"] == rid and claims["uid"] == uid


def test_fcm_message_with_actions_is_data_only():
    from app.services.notify import fcm_message

    with_actions = fcm_message("t", "⏰ Erinnerung", "Müll", {"actions": "done", "route": "/reminders"}, "reminder")
    assert "notification" not in with_actions
    assert with_actions["data"]["title"] == "⏰ Erinnerung" and with_actions["data"]["body"] == "Müll"
    plain = fcm_message("t", "Hallo", "Text", {"route": "/"}, "system")
    assert plain["notification"] == {"title": "Hallo", "body": "Text"}
    assert plain["android"]["notification"]["channel_id"] == "system"


def test_today_uses_local_day_boundaries(client):
    h, _ = _auth(client, "ra_h")
    now = datetime.now(BERLIN)
    just_after_midnight = now.replace(hour=0, minute=30, second=0, microsecond=0)
    yesterday_late = just_after_midnight - timedelta(hours=1)
    client.post("/api/reminders", headers=h, json={"title": "Heute früh", "due_at": just_after_midnight.isoformat()})
    client.post("/api/reminders", headers=h, json={"title": "Gestern spät", "due_at": yesterday_late.isoformat()})
    titles = [r["title"] for r in client.get("/api/today", headers=h).json()["reminders"]]
    assert "Heute früh" in titles and "Gestern spät" not in titles
