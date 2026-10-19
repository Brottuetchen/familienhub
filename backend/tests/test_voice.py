"""Voice endpoints (/api/voice): speech texts, scopes, roles, spoken times, sources that are down (#21)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.core.timeutil import local_tz
from app.models.reminder import Reminder
from app.models.user import User
from app.routers.voice import split_items
from app.services.voice_time import parse_when

BERLIN = ZoneInfo("Europe/Berlin")


def _user(name, role="partner", language=None, full_name=None):
    with SessionLocal() as db:
        u = db.query(User).filter(User.username == name).first()
        if not u:
            u = User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"),
                     role=role, is_admin=role == "admin", language=language, full_name=full_name)
            db.add(u)
            db.commit()
            db.refresh(u)
        return u.id


def _login(client, name, role="partner", **kw):
    _user(name, role, **kw)
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _key(client, name, scopes=("voice",), role="partner", **kw):
    """Headers with a (scoped) API key of that person."""
    session = _login(client, name, role, **kw)
    body = {"name": "Assist"} if scopes is None else {"name": "Assist", "scopes": list(scopes)}
    created = client.post("/api/auth/api-tokens", headers=session, json=body)
    assert created.status_code == 201, created.text
    return {"Authorization": f"Bearer {created.json()['token']}"}


# --- spoken times ---------------------------------------------------------------------------------------

def _at(h, m=0, day=19):
    return datetime(2026, 10, day, h, m, tzinfo=BERLIN)


NOW = _at(7, 0)


@pytest.mark.parametrize("text,expected", [
    ("at 6", _at(18)),                       # 07:00 -> the next 6 o'clock is the evening one
    ("um 6", _at(18)),
    ("18:30", _at(18, 30)),
    ("18.30", _at(18, 30)),
    ("6:30", _at(18, 30)),
    ("6 pm", _at(18)),
    ("6:30 PM", _at(18, 30)),
    ("5 am", _at(5, day=20)),                # already over today -> tomorrow
    ("12 am", _at(0, day=20)),
    ("um 6 Uhr", _at(6, day=20)),            # German "6 Uhr" is 06:00, already over
    ("um 18 Uhr 30", _at(18, 30)),
    ("7 Uhr 15", _at(7, 15)),
    ("um 06:00", _at(6, day=20)),
    ("in 20 minutes", _at(7, 20)),
    ("in 20 Minuten", _at(7, 20)),
    ("in 1 hour", _at(8)),
    ("in einer Stunde", _at(8)),
    ("in an hour", _at(8)),
    ("in half an hour", _at(7, 30)),
    ("in einer halben Stunde", _at(7, 30)),
    ("in 2 hours and 15 minutes", _at(9, 15)),
    ("in zwanzig Minuten", _at(7, 20)),
    ("tomorrow at 8", _at(8, day=20)),
    ("tomorrow at 6", _at(18, day=20)),      # with a day, 1-6 are afternoon
    ("morgen um halb sieben", _at(6, 30, day=20)),
    ("morgen früh um 7", _at(7, day=20)),
    ("today at 9 pm", _at(21)),
    ("heute Abend um 8", _at(20)),
    ("tonight at 9", _at(21)),
    ("übermorgen um 10 Uhr", _at(10, day=21)),
    ("friday at 3", _at(15, day=23)),
    ("am Freitag um 15 Uhr", _at(15, day=23)),
    ("quarter past 6", _at(18, 15)),
    ("viertel vor sieben", _at(18, 45)),
    ("noon", _at(12)),
    ("midnight", _at(0, day=20)),
    ("tomorrow", _at(9, day=20)),            # only a day: 09:00
    ("  At 6.  ", _at(18)),
])
def test_parse_when(text, expected):
    assert parse_when(text, NOW) == expected


@pytest.mark.parametrize("text", ["", "   ", "banana", "at 25", "at 99", "13 pm", "in 0 minutes", "in 99999 hours",
                                  "x" * 200])
def test_parse_when_rejects(text):
    assert parse_when(text, NOW) is None


def test_parse_when_picks_the_next_occurrence_by_clock():
    assert parse_when("at 6", _at(5, 0)) == _at(6)          # 05:00 -> 06:00 this morning
    assert parse_when("at 6", _at(17, 59)) == _at(18)
    assert parse_when("at 6", _at(18, 0)) == _at(6, day=20)  # 18:00 is no longer ahead
    assert parse_when("at 12", _at(11, 0)) == _at(12)


def test_parse_when_keeps_wall_clock_across_dst_change():
    # Europe/Berlin leaves summer time on 2026-10-25: "tomorrow at 8" stays 08:00 local
    saturday = datetime(2026, 10, 24, 20, 0, tzinfo=BERLIN)
    got = parse_when("tomorrow at 8", saturday)
    assert (got.day, got.hour, got.minute) == (25, 8, 0) and got.utcoffset() == timedelta(hours=1)


def test_split_items():
    assert split_items("milk, bread and eggs") == ["Milk", "Bread", "Eggs"]
    assert split_items("Milch, Brot und Eier") == ["Milch", "Brot", "Eier"]
    assert split_items("some milk & the bread") == ["Milk", "Bread"]
    assert split_items(["milk and butter", "milk"]) == ["Milk", "Butter"]
    assert split_items(" , and ,") == []
    assert len(split_items(",".join(f"item{i}" for i in range(50)))) == 20


# --- auth, scopes, language -----------------------------------------------------------------------------

def test_voice_needs_authentication(client):
    assert client.get("/api/voice/shopping").status_code == 401
    assert client.post("/api/voice/shopping/items", json={"items": "milk"}).status_code == 401


def test_scoped_key_only_reaches_voice_and_only_its_scopes(client):
    key = _key(client, "v_scope", scopes=["shopping:read"])
    assert client.get("/api/voice/shopping", headers=key).status_code == 200
    # missing scope
    r = client.post("/api/voice/shopping/items", headers=key, json={"items": "milk"})
    assert r.status_code == 403 and "shopping:write" in r.json()["detail"]
    assert client.get("/api/voice/meals", headers=key).status_code == 403
    assert client.post("/api/voice/reminders", headers=key, json={"text": "x", "when": "in 5 minutes"}).status_code == 403
    # the normal API is closed to scoped keys
    assert client.get("/api/auth/me", headers=key).status_code == 403
    assert client.get("/api/shopping", headers=key).status_code == 403
    assert client.get("/api/today", headers=key).status_code == 403


def test_voice_preset_covers_every_voice_scope(client):
    session = _login(client, "v_preset")
    created = client.post("/api/auth/api-tokens", headers=session, json={"name": "A", "scopes": ["voice"]}).json()
    assert set(created["scopes"]) == {"shopping:read", "shopping:write", "tasks:write", "meals:read",
                                      "calendar:read", "reminders:write"}
    listed = client.get("/api/auth/api-tokens", headers=session).json()
    assert listed[0]["scopes"] == created["scopes"]


def test_unknown_scope_rejected_and_unscoped_key_stays_unrestricted(client):
    session = _login(client, "v_unknown")
    bad = client.post("/api/auth/api-tokens", headers=session, json={"name": "A", "scopes": ["admin:all"]})
    assert bad.status_code == 400
    assert client.post("/api/auth/api-tokens", headers=session, json={"name": "A", "scopes": []}).status_code == 400
    old = _key(client, "v_old", scopes=None)  # created like before scopes existed
    assert client.get("/api/auth/me", headers=old).status_code == 200
    assert client.get("/api/voice/shopping", headers=old).status_code == 200


def test_app_session_works_without_scopes(client):
    assert client.get("/api/voice/shopping", headers=_login(client, "v_session")).status_code == 200


def test_language_of_owner_and_overrides(client):
    de = _key(client, "v_lang_de", language="de")
    en = _key(client, "v_lang_en", language="en")
    assert client.get("/api/voice/shopping", headers=de).json()["lang"] == "de"
    r = client.get("/api/voice/shopping", headers=en).json()
    assert r["lang"] == "en"
    # explicit query parameter beats the owner's language, Accept-Language beats it too
    assert client.get("/api/voice/shopping", headers=en, params={"lang": "de"}).json()["lang"] == "de"
    assert client.get("/api/voice/shopping", headers={**de, "Accept-Language": "en-US,en;q=0.9"}).json()["lang"] == "en"
    # unsupported language falls back to the owner's
    assert client.get("/api/voice/shopping", headers=en, params={"lang": "fr"}).json()["lang"] == "en"
    # nobody set a language: German (project default)
    assert client.get("/api/voice/shopping", headers=_key(client, "v_lang_none")).json()["lang"] == "de"


# --- shopping -------------------------------------------------------------------------------------------

def test_add_and_list_shopping_items(client):
    key = _key(client, "v_shop", language="en")
    r = client.post("/api/voice/shopping/items", headers=key, json={"items": "oat milk, bread and eggs"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["status"] == "ok"
    assert body["added"] == ["Oat milk", "Bread", "Eggs"]
    assert body["speech"] == "Added Oat milk, Bread and Eggs to the shopping list."

    listed = client.get("/api/voice/shopping", headers=key).json()
    assert listed["ok"] and {"Oat milk", "Bread", "Eggs"} <= set(listed["items"])
    assert listed["count"] == len(listed["items"])
    assert "on the shopping list" in listed["speech"]

    # the same entries are on the normal list (same source as the app)
    app_list = client.get("/api/shopping", headers=_login(client, "v_shop")).json()
    assert "Oat milk" in [i["summary"] for g in app_list["groups"] for i in g["items"]]


def test_add_shopping_german_and_list_input(client):
    key = _key(client, "v_shop_de", language="de")
    one = client.post("/api/voice/shopping/items", headers=key, json={"items": "Butter"}).json()
    assert one["speech"] == "Butter steht auf der Einkaufsliste."
    many = client.post("/api/voice/shopping/items", headers=key, json={"items": ["Käse und Wurst"]}).json()
    assert many["added"] == ["Käse", "Wurst"] and many["speech"] == "Käse und Wurst stehen auf der Einkaufsliste."


def test_add_shopping_nothing_understood(client):
    key = _key(client, "v_shop_empty", language="en")
    r = client.post("/api/voice/shopping/items", headers=key, json={"items": " , and "}).json()
    assert not r["ok"] and r["status"] == "invalid" and r["speech"] == "What should I put on the shopping list?"
    assert client.post("/api/voice/shopping/items", headers=key, json={}).json()["status"] == "invalid"


def test_shopping_source_unavailable_is_spoken(client, monkeypatch):
    from app.routers import shopping

    key = _key(client, "v_shop_down", language="en")

    async def down(*a, **k):
        raise HTTPException(503, "Home Assistant not configured")

    monkeypatch.setattr(shopping, "add_item", down)
    r = client.post("/api/voice/shopping/items", headers=key, json={"items": "milk"})
    assert r.status_code == 200
    assert r.json()["status"] == "unavailable" and r.json()["speech"] == "The shopping list is not reachable right now."

    async def down_list(*a, **k):
        return {"status": "unavailable", "error": "boom", "groups": []}

    monkeypatch.setattr(shopping, "list_items", down_list)
    r = client.get("/api/voice/shopping", headers=key).json()
    assert not r["ok"] and r["status"] == "unavailable" and r["items"] == []

    async def crash(*a, **k):
        raise RuntimeError("no connection")

    monkeypatch.setattr(shopping, "list_items", crash)
    assert client.get("/api/voice/shopping", headers=key).json()["status"] == "unavailable"


def test_shopping_partial_failure(client, monkeypatch):
    from app.routers import shopping

    key = _key(client, "v_shop_partial", language="en")
    real = shopping.add_item

    async def flaky(data, user, idem=None):
        if data.item == "Bread":
            raise HTTPException(502, "Could not add item")
        return await real(data, user, idem)

    monkeypatch.setattr(shopping, "add_item", flaky)
    r = client.post("/api/voice/shopping/items", headers=key, json={"items": "milk, bread"}).json()
    assert not r["ok"] and r["status"] == "partial" and r["added"] == ["Milk"] and r["failed"] == ["Bread"]
    assert r["speech"] == "I could only add 1 of 2 items to the shopping list."


def test_guest_may_add_to_the_shopping_list_like_in_the_app(client):
    key = _key(client, "v_shop_guest", role="guest", language="en")
    assert client.post("/api/voice/shopping/items", headers=key, json={"items": "tea"}).json()["ok"] is True


# --- tasks ----------------------------------------------------------------------------------------------

def _hub_task_titles(client, headers, view="all"):
    acc = [p for p in client.get("/api/tasks/providers", headers=headers).json()["items"] if p["id"] == "hub_tasks"][0]["account"]
    r = client.get("/api/tasks", params={"provider": "hub_tasks", "view": view, "account": acc}, headers=headers)
    return {t["title"] for t in r.json()["items"]}


def test_add_task_for_myself_and_for_a_named_person(client):
    key = _key(client, "v_task_owner", language="en")
    owner = _login(client, "v_task_owner")
    _user("v_task_anna", full_name="Voxanna Voice")
    anna = _login(client, "v_task_anna")

    own = client.post("/api/voice/tasks", headers=key, json={"title": "take out the trash"}).json()
    assert own["ok"] and own["speech"] == "Okay, I added the task Take out the trash." and own["assignee"] is None

    other = client.post("/api/voice/tasks", headers=key, json={"title": "water the plants", "assignee": "Voxanna"}).json()
    assert other["ok"] and other["assignee"] == "Voxanna Voice"
    assert other["speech"] == "Okay, I added the task Water the plants for Voxanna Voice."
    assert "Water the plants" in _hub_task_titles(client, anna, "for_me")
    assert "Take out the trash" in _hub_task_titles(client, owner, "mine")

    # "me" in both languages means the owner
    assert client.post("/api/voice/tasks", headers=key, json={"title": "Self", "assignee": "mir"}).json()["assignee"] is None


def test_add_task_person_unknown_ambiguous_or_missing_title(client):
    key = _key(client, "v_task_names", language="en")
    _user("v_twin_a", full_name="Twin Voice")
    _user("v_twin_b", full_name="Twin Other")
    r = client.post("/api/voice/tasks", headers=key, json={"title": "x", "assignee": "Nobodyatall"}).json()
    assert not r["ok"] and r["status"] == "not_found" and r["speech"] == "I do not know anyone called Nobodyatall."
    r = client.post("/api/voice/tasks", headers=key, json={"title": "x", "assignee": "twin"}).json()
    assert r["status"] == "ambiguous"
    r = client.post("/api/voice/tasks", headers=key, json={"title": "  "}).json()
    assert r["status"] == "invalid" and r["speech"] == "What should the task be?"


def test_guests_are_never_task_recipients(client):
    key = _key(client, "v_task_guest_ref", language="en")
    _user("v_guest_person", role="guest", full_name="Gina Guest")
    assert client.post("/api/voice/tasks", headers=key, json={"title": "x", "assignee": "Gina"}).json()["status"] == "not_found"


@pytest.mark.parametrize("role", ["child", "guest"])
def test_tasks_need_an_adult(client, role):
    key = _key(client, f"v_task_{role}", role=role, language="en")
    r = client.post("/api/voice/tasks", headers=key, json={"title": "Homework"})
    assert r.status_code == 200 and r.json()["status"] == "forbidden"
    assert r.json()["speech"] == "Only adults can add tasks."


def test_task_source_unavailable_is_spoken(client, monkeypatch):
    from app.routers import tasks

    key = _key(client, "v_task_down", language="de")

    async def down(*a, **k):
        raise HTTPException(409, "No task place available")

    monkeypatch.setattr(tasks, "_create_task", down)
    r = client.post("/api/voice/tasks", headers=key, json={"title": "x"}).json()
    assert not r["ok"] and r["status"] == "unavailable" and r["speech"] == "Ich konnte die Aufgabe gerade nicht speichern."


# --- meals ----------------------------------------------------------------------------------------------

def _plan(client, headers, day, title, meal_type="dinner"):
    r = client.post("/api/meals/plan", headers=headers,
                    json={"date": day.isoformat(), "custom_title": title, "meal_type": meal_type})
    assert r.status_code in (200, 201), r.text


def _local_today():
    return datetime.now(local_tz()).date()


def test_meals_today_and_tomorrow(client):
    key = _key(client, "v_meal_plan", language="en")
    adult = _login(client, "v_meal_plan")
    today = _local_today()
    _plan(client, adult, today, "Lasagne")
    _plan(client, adult, today + timedelta(days=1), "Pancakes", "lunch")
    now = client.get("/api/voice/meals", headers=key).json()
    # other tests may plan meals for the same days: look for ours
    assert now["ok"] and "Lasagne" in [m["title"] for m in now["meals"]] and now["date"] == today.isoformat()
    assert now["speech"].startswith("On the menu today: ") and "Lasagne" in now["speech"]
    nxt = client.get("/api/voice/meals", headers=key, params={"day": "tomorrow"}).json()
    assert nxt["speech"].startswith("On the menu tomorrow: ") and "Pancakes" in nxt["speech"]
    de = client.get("/api/voice/meals", headers=key, params={"day": "morgen", "lang": "de"}).json()
    assert de["speech"].startswith("Es gibt morgen: ") and "Pancakes" in de["speech"]


def test_meals_several_meals_name_their_type(client):
    key = _key(client, "v_meal_many", language="en")
    adult = _login(client, "v_meal_many")
    day = _local_today() + timedelta(days=3)
    _plan(client, adult, day, "Soup", "lunch")
    _plan(client, adult, day, "Fish", "dinner")
    r = client.get("/api/voice/meals", headers=key, params={"day": day.isoformat()}).json()
    assert r["ok"] and "lunch: Soup" in r["speech"] and "dinner: Fish" in r["speech"]


def test_meals_nothing_planned_and_bad_day(client):
    key = _key(client, "v_meal_none", language="en")
    far = (_local_today() + timedelta(days=200)).isoformat()
    r = client.get("/api/voice/meals", headers=key, params={"day": far}).json()
    assert r["ok"] and r["meals"] == [] and r["speech"].startswith("Nothing is planned")
    bad = client.get("/api/voice/meals", headers=key, params={"day": "someday"}).json()
    assert not bad["ok"] and bad["status"] == "invalid"


def test_meal_source_unavailable_is_spoken(client, monkeypatch):
    from app.routers import meals

    key = _key(client, "v_meal_down", language="en")

    async def down(*a, **k):
        return {"status": "unavailable", "error": "Cookidoo down", "days": []}

    monkeypatch.setattr(meals, "get_meals", down)
    r = client.get("/api/voice/meals", headers=key).json()
    assert not r["ok"] and r["status"] == "unavailable" and r["speech"] == "The meal plan is not reachable right now."

    async def crash(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(meals, "get_meals", crash)
    assert client.get("/api/voice/meals", headers=key).json()["status"] == "unavailable"


def test_meals_readable_by_guest(client):
    key = _key(client, "v_meal_guest", role="guest")
    assert client.get("/api/voice/meals", headers=key).status_code == 200


# --- events ---------------------------------------------------------------------------------------------

def _event(start_local: datetime, title, all_day=False):
    return {"title": title, "start": start_local.isoformat(), "end": (start_local + timedelta(hours=1)).isoformat(),
            "all_day": all_day, "calendar": "Test"}


def test_events_today_tomorrow_and_all_day(client, monkeypatch):
    from app.routers import calendar

    today = _local_today()
    noon = datetime.combine(today, datetime.min.time()).replace(hour=15, minute=30)
    tomorrow_9 = noon.replace(hour=9, minute=0) + timedelta(days=1)
    day_start = datetime.combine(today, datetime.min.time())
    rows = [_event(noon, "Dentist"),
            {"title": "Birthday", "start": day_start.date().isoformat(),
             "end": (day_start.date() + timedelta(days=1)).isoformat(), "all_day": True},
            _event(tomorrow_9, "Parents evening")]

    async def fake(db, user, days, start=None):
        return rows

    monkeypatch.setattr(calendar, "collect_events", fake)
    key = _key(client, "v_events", language="en")
    r = client.get("/api/voice/events", headers=key).json()
    assert r["ok"] and [e["title"] for e in r["events"]] == ["Dentist", "Birthday"]
    assert r["speech"] == "2 events today: Dentist at 3:30 PM and Birthday, all day."
    t = client.get("/api/voice/events", headers=key, params={"day": "tomorrow", "lang": "de"}).json()
    assert [e["title"] for e in t["events"]] == ["Parents evening"]
    assert t["speech"] == "Morgen ein Termin: Parents evening um 9 Uhr."


def test_events_none_and_source_unavailable(client, monkeypatch):
    from app.routers import calendar

    key = _key(client, "v_events_none", language="en")

    async def empty(db, user, days, start=None):
        return []

    monkeypatch.setattr(calendar, "collect_events", empty)
    r = client.get("/api/voice/events", headers=key).json()
    assert r["ok"] and r["speech"] == "No events today."

    async def down(db, user, days, start=None):
        raise RuntimeError("CalDAV down")

    monkeypatch.setattr(calendar, "collect_events", down)
    r = client.get("/api/voice/events", headers=key)
    assert r.status_code == 200 and r.json()["status"] == "unavailable"
    assert r.json()["speech"] == "The calendar is not reachable right now."
    assert client.get("/api/voice/events", headers=key, params={"day": "x"}).json()["status"] == "invalid"


# --- reminders ------------------------------------------------------------------------------------------

def _stored(client, name):
    with SessionLocal() as db:
        uid = db.query(User).filter(User.username == name).one().id
        return db.query(Reminder).filter(Reminder.created_by == uid).order_by(Reminder.id.desc()).first()


def test_reminder_in_20_minutes(client):
    key = _key(client, "v_rem_rel", language="en")
    before = datetime.utcnow()
    r = client.post("/api/voice/reminders", headers=key, json={"text": "call Grandma", "when": "in 20 minutes"}).json()
    assert r["ok"] and r["title"] == "Call Grandma"
    row = _stored(client, "v_rem_rel")
    assert row.title == "Call Grandma" and row.source == "user" and not row.for_family
    assert timedelta(minutes=19) < row.due_at - before < timedelta(minutes=21)  # stored as naive UTC
    assert r["speech"].startswith("Okay, I will remind you ") and r["speech"].endswith(" to call Grandma.")
    assert " at " in r["speech"]


def test_reminder_at_clock_time_uses_the_hub_timezone(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "timezone", "America/New_York")
    key = _key(client, "v_rem_tz", language="en")
    r = client.post("/api/voice/reminders", headers=key, json={"text": "stretch", "when": "tomorrow at 8"}).json()
    assert r["ok"]
    tz = ZoneInfo("America/New_York")
    expected = (datetime.now(tz) + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
    due = _stored(client, "v_rem_tz").due_at
    assert due == expected.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    assert r["speech"] == "Okay, I will remind you tomorrow at 8 AM to stretch."
    assert r["due_at"].startswith(expected.date().isoformat() + "T08:00:00")


def test_reminder_german_speech(client):
    key = _key(client, "v_rem_de", language="de")
    r = client.post("/api/voice/reminders", headers=key, json={"text": "Oma anrufen", "when": "morgen um halb sieben"}).json()
    assert r["ok"] and r["speech"] == "Okay, ich erinnere dich morgen um 6:30 Uhr: Oma anrufen."


def test_reminder_bad_input_is_spoken(client):
    key = _key(client, "v_rem_bad", language="en")
    no_time = client.post("/api/voice/reminders", headers=key, json={"text": "x", "when": "whenever"}).json()
    assert not no_time["ok"] and no_time["status"] == "invalid" and "did not understand the time" in no_time["speech"]
    no_text = client.post("/api/voice/reminders", headers=key, json={"text": " ", "when": "at 6"}).json()
    assert no_text["speech"] == "What should I remind you of?"
    past = client.post("/api/voice/reminders", headers=key, json={"text": "x", "when": "today at 00:00"}).json()
    assert past["status"] == "invalid" and past["speech"] == "That time has already passed."
    assert _stored(client, "v_rem_bad") is None


def test_child_and_guest_may_set_their_own_reminder(client):
    for role in ("child", "guest"):
        key = _key(client, f"v_rem_{role}", role=role)
        assert client.post("/api/voice/reminders", headers=key, json={"text": "x", "when": "in 5 minutes"}).json()["ok"]
        row = _stored(client, f"v_rem_{role}")
        assert row.for_family is False  # never a family-wide reminder from the voice endpoint


def test_reminder_is_private_to_its_owner(client):
    key = _key(client, "v_rem_owner")
    client.post("/api/voice/reminders", headers=key, json={"text": "secret gift", "when": "in 5 minutes"})
    other = _login(client, "v_rem_other")
    assert "Secret gift" not in [r["title"] for r in client.get("/api/reminders", headers=other).json()]
