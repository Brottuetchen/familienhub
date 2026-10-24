"""Plugin extension points: Today cards, notifications, scheduled jobs, connection test (docs/plugins.md).

Fake plugins are registered in the real registry; the hub code under test (sanitising, timeouts, layout,
notification service, scheduler) is the real one.
"""

import asyncio

import pytest

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.notification_log import NotificationLog
from app.models.notification_prefs import NotificationPreference
from app.models.user import User
from app.plugins import Plugin, Setting, jobs
from app.plugins import api as plugin_api
from app.plugins import hooks
from app.plugins.registry import plugin_registry
from app.config import settings

ME = "/api/me/today-layout"


class Fake(Plugin):
    """A plugin whose hooks are replaced per test."""

    def __init__(self, pid="ext_demo", **kw):
        super().__init__(id=pid, name="Ext demo", **kw)
        self.cards = []
        self.card_calls = 0
        self.job_calls = 0
        self.job = None
        self.test = None

    async def today_cards(self, user, db):
        self.card_calls += 1
        if isinstance(self.cards, Exception):
            raise self.cards
        if callable(self.cards):
            return await self.cards(user, db)
        return self.cards

    async def scheduled(self, db):
        self.job_calls += 1
        if self.job:
            await self.job(db)

    async def test_settings(self, values):
        return await self.test(values)


@pytest.fixture
def make_plugin():
    made = []

    def make(pid="ext_demo", **kw):
        plugin = Fake(pid, **kw)
        assert plugin_registry.register(plugin)
        made.append(plugin)
        return plugin

    yield make
    for p in made:
        plugin_registry.unregister(p.id)
    jobs.reset()
    plugin_api.reset_limits()


def _person(client, name, role="partner"):
    with SessionLocal() as db:
        if not db.query(User).filter(User.username == name).first():
            db.add(User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"),
                        role=role, full_name=name.title()))
            db.commit()
        uid = db.query(User).filter(User.username == name).first().id
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}, uid


GOOD = {"id": "weather", "title": "Garbage", "icon": "delete_outline",
        "lines": [{"text": "Paper tomorrow", "secondary": "6 am"}, {"text": "Plastic"}],
        "image": "/api/plugins/ext_demo/img/1.png", "link": "https://example.org/x", "badge": "2"}


# --- Today cards: sanitising ---

def test_card_is_passed_on_with_plugin_and_key(make_plugin):
    card = hooks.sanitize_card(make_plugin(), GOOD)
    assert card == {"key": "plugin:ext_demo:weather", "plugin": "ext_demo", "plugin_name": "Ext demo",
                    "id": "weather", "title": "Garbage", "icon": "delete_outline",
                    "lines": [{"text": "Paper tomorrow", "secondary": "6 am"}, {"text": "Plastic", "secondary": None}],
                    "image": "/api/plugins/ext_demo/img/1.png", "link": "https://example.org/x", "badge": "2",
                    "slides": []}


def test_slides_keep_valid_pictures_only_and_are_limited(make_plugin):
    slides = [
        {"image": "/api/plugins/ext_demo/img/1.png", "caption": "3 years ago", "secondary": "20.10.2023",
         "link": "https://photos.example.org/photos/1"},
        {"image": "/api/plugins/other/img.png", "caption": "foreign"},       # other plugin: dropped
        {"image": "/api/plugins/ext_demo/img/2.png", "caption": "x\ny" * 100, "link": "http://insecure.example"},
        "not a slide", {"caption": "no picture"},
    ]
    plugin = make_plugin()
    card = hooks.sanitize_card(plugin, {**GOOD, "slides": slides})
    assert [s["image"] for s in card["slides"]] == ["/api/plugins/ext_demo/img/1.png", "/api/plugins/ext_demo/img/2.png"]
    assert card["slides"][0] == {"image": "/api/plugins/ext_demo/img/1.png", "caption": "3 years ago",
                                 "secondary": "20.10.2023", "link": "https://photos.example.org/photos/1"}
    second = card["slides"][1]
    assert second["link"] is None and second["secondary"] is None and len(second["caption"]) <= hooks.MAX_LINE
    assert "\n" not in second["caption"]
    many = [{"image": f"/api/plugins/ext_demo/img/{i}.png"} for i in range(30)]
    assert len(hooks.sanitize_card(plugin, {**GOOD, "slides": many})["slides"]) == hooks.MAX_SLIDES
    assert hooks.sanitize_card(plugin, {**GOOD, "slides": "nope"})["slides"] == []


@pytest.mark.parametrize("image", [
    "/api/plugins/other/img.png", "https://evil.example/x.png", "//evil.example/x.png", "/api/plugins/ext_demo/",
    "/api/plugins/ext_demo/../../auth/me", "/api/plugins/ext_demo/%2e%2e/auth", "/api/plugins/ext_demo//x",
    "/api/plugins/ext_demo/a b", "/api/plugins/ext_demo/a\\b", "/api/plugins/ext_demo/" + "a" * 400, 5, ["x"],
    "/api/me", "api/plugins/ext_demo/x",
])
def test_invalid_image_is_dropped_but_card_stays(make_plugin, image):
    card = hooks.sanitize_card(make_plugin(), {**GOOD, "image": image})
    assert card is not None and card["image"] is None and card["title"] == "Garbage"


@pytest.mark.parametrize("link", ["http://example.org", "javascript:alert(1)", "ftp://x.org", "https://", "//x.org",
                                  "https://exa mple.org", "https://user@evil.org/", 7])
def test_only_https_links_survive(make_plugin, link):
    assert hooks.sanitize_card(make_plugin(), {**GOOD, "link": link})["link"] is None


def test_limits_and_fallbacks(make_plugin):
    plugin = make_plugin()
    card = hooks.sanitize_card(plugin, {
        "id": "c1", "title": "T" * 200, "icon": "not-an-icon", "badge": "B" * 40,
        "lines": [{"text": f"line {i}"} for i in range(20)] + [{"text": ""}, 5],
    })
    assert len(card["title"]) <= hooks.MAX_TITLE and card["title"].endswith("…")
    assert card["icon"] == hooks.DEFAULT_ICON and len(card["badge"]) <= hooks.MAX_BADGE
    assert len(card["lines"]) == hooks.MAX_LINES
    line = hooks.sanitize_card(plugin, {"id": "c", "title": "x", "lines": [{"text": "a" * 500, "secondary": "b" * 500}]})
    assert len(line["lines"][0]["text"]) <= hooks.MAX_LINE and len(line["lines"][0]["secondary"]) <= hooks.MAX_LINE
    assert hooks.sanitize_card(plugin, {"id": "c", "title": "line\nbreak\x00"})["title"] == "line break"


@pytest.mark.parametrize("raw", [None, "x", 3, [], {"title": "no id"}, {"id": "ok"}, {"id": "bad id", "title": "x"},
                                 {"id": "a:b", "title": "x"}, {"id": "x" * 41, "title": "x"}, {"id": 5, "title": "x"},
                                 {"id": "ok", "title": "   "}])
def test_unusable_cards_are_dropped(make_plugin, raw):
    assert hooks.sanitize_card(make_plugin(), raw) is None


def test_duplicates_and_count_are_limited(make_plugin):
    plugin = make_plugin()
    raw = [{"id": "a", "title": "one"}, {"id": "a", "title": "again"}] + [{"id": f"c{i}", "title": "x"} for i in range(10)]
    cards = hooks.sanitize_cards(plugin, raw)
    assert [c["id"] for c in cards][:2] == ["a", "c0"] and len(cards) == hooks.MAX_CARDS_PER_PLUGIN
    assert hooks.sanitize_cards(plugin, "not a list") == []


# --- Today cards: in GET /api/today ---

def test_today_contains_the_cards_of_active_plugins(client, auth, make_plugin):
    plugin = make_plugin()
    plugin.cards = [GOOD, {"id": "junk"}]
    body = client.get("/api/today", headers=auth).json()
    assert [c["key"] for c in body["plugin_cards"]] == ["plugin:ext_demo:weather"]
    assert body["plugin_cards"][0]["lines"][0] == {"text": "Paper tomorrow", "secondary": "6 am"}


def test_card_hook_gets_the_requesting_person(client, make_plugin):
    seen = []

    async def cards(user, db):
        seen.append(user.username)
        return [{"id": "me", "title": f"Hi {user.username}"}]

    make_plugin().cards = cards
    headers, _ = _person(client, "ext_mom")
    body = client.get("/api/today", headers=headers).json()
    assert seen == ["ext_mom"] and body["plugin_cards"][0]["title"] == "Hi ext_mom"


def test_failing_and_slow_plugins_never_break_today(client, auth, make_plugin, monkeypatch):
    bad, slow, good = make_plugin("ext_bad"), make_plugin("ext_slow"), make_plugin("ext_good")
    bad.cards = RuntimeError("boom")

    async def hang(user, db):
        await asyncio.sleep(30)

    slow.cards = hang
    good.cards = [{"id": "ok", "title": "Fine"}]
    monkeypatch.setattr(hooks, "TODAY_CARDS_TIMEOUT", 0.2)
    r = client.get("/api/today", headers=auth)
    assert r.status_code == 200
    assert [c["key"] for c in r.json()["plugin_cards"]] == ["plugin:ext_good:ok"]


def test_plugin_with_missing_required_setting_runs_no_hooks(client, auth, make_plugin):
    plugin = make_plugin("ext_setup", settings=(Setting("EXT_SETUP_URL", "Address"),))
    plugin.cards = [{"id": "a", "title": "x"}]
    plugin.schedule_minutes = 5
    assert not plugin.active and plugin.describe()["needs_setup"] is True
    assert client.get("/api/today", headers=auth).json()["plugin_cards"] == []
    asyncio.run(jobs.run_due(wait=True))
    assert plugin.card_calls == 0 and plugin.job_calls == 0


def test_disabled_plugin_runs_no_hooks(client, auth, make_plugin, monkeypatch):
    plugin = make_plugin()
    plugin.cards = [{"id": "a", "title": "x"}]
    monkeypatch.setattr(settings, "plugins_disabled", "ext_demo")
    assert client.get("/api/today", headers=auth).json()["plugin_cards"] == []
    assert plugin.card_calls == 0 and plugin.describe()["needs_setup"] is False


def test_plain_plugin_costs_nothing(client, auth):
    assert client.get("/api/today", headers=auth).json()["plugin_cards"] == []


# --- Today layout with plugin cards ---

def _cards(*ids, hidden=()):
    return [{"id": i, "visible": i not in hidden, "size": "full"} for i in ids]


def test_layout_accepts_cards_of_active_plugins_only(client, auth, make_plugin, monkeypatch):
    make_plugin()
    headers, _ = _person(client, "ext_layout")
    client.delete(ME, headers=headers)
    ok = client.put(ME, headers=headers, json={"cards": _cards("plugin:ext_demo:weather", "tasks", hidden=("tasks",))})
    assert ok.status_code == 200
    ids = [c["id"] for c in ok.json()["cards"]]
    assert ids[:2] == ["plugin:ext_demo:weather", "tasks"] and "stars" in ids  # built-in cards still appended
    for bad in ("plugin:ext_demo", "plugin:ext_demo:a:b", "plugin::x", "plugin:ext_demo:bad id", "plugin:ext_demo:",
                "plugin:Bad:x"):
        r = client.put(ME, headers=headers, json={"cards": _cards(bad)})
        assert r.status_code == 422, bad
    # A card of a plugin that is not (or no longer) active, e.g. from an app's stale cache: saved without error,
    # the card itself is dropped
    r = client.put(ME, headers=headers, json={"cards": _cards("plugin:nobody:weather", "plugin:ext_demo:weather")})
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()["cards"]]
    assert "plugin:nobody:weather" not in ids and ids[0] == "plugin:ext_demo:weather"
    # Switching the plugin off drops its card from the stored layout when it is read
    monkeypatch.setattr(settings, "plugins_disabled", "ext_demo")
    assert "plugin:ext_demo:weather" not in [c["id"] for c in client.get(ME, headers=headers).json()["cards"]]
    monkeypatch.setattr(settings, "plugins_disabled", "")
    client.delete(ME, headers=headers)


def test_family_default_may_hold_plugin_cards(client, auth, make_plugin):
    make_plugin()
    r = client.put("/api/admin/today-layout", headers=auth, json={"cards": _cards("plugin:ext_demo:x", "events")})
    try:
        assert r.status_code == 200 and r.json()["cards"][0]["id"] == "plugin:ext_demo:x"
    finally:
        client.delete("/api/admin/today-layout", headers=auth)


# --- Notifications ---

def _log(uid):
    with SessionLocal() as db:
        return db.query(NotificationLog).filter(NotificationLog.user_id == uid).order_by(NotificationLog.id).all()


def test_notify_reaches_people_and_roles_in_category_plugins(client, make_plugin, monkeypatch):
    monkeypatch.setattr(plugin_api, "MAX_RECIPIENTS", 10000)  # the suite creates many partners
    make_plugin()
    _, mom = _person(client, "ext_n_mom")
    _, kid = _person(client, "ext_n_kid", "child")
    before = {u: len(_log(u)) for u in (mom, kid)}
    r = asyncio.run(plugin_api.notify("ext_demo", user_ids=[kid], title="Bus is late", body="10 min",
                                      url="https://example.org/bus", data={"route": "/today", "extra": 5}))
    assert r == {"recipients": 1, "delivered": 0, "sent": True, "reason": None}
    assert len(_log(mom)) == before[mom] and len(_log(kid)) == before[kid] + 1
    entry = _log(kid)[-1]
    assert (entry.title, entry.body, entry.category, entry.source, entry.route) == (
        "Bus is late", "10 min", "plugins", "plugin:ext_demo", "/today")
    r = asyncio.run(plugin_api.notify("ext_demo", roles=["partner"], title="For parents"))
    assert r["sent"] and r["recipients"] >= 1
    assert _log(mom)[-1].title == "For parents" and _log(kid)[-1].title == "Bus is late"


def test_notify_caps_the_number_of_recipients(client, make_plugin, monkeypatch):
    make_plugin()
    for i in range(3):
        _person(client, f"ext_cap{i}")
    monkeypatch.setattr(plugin_api, "MAX_RECIPIENTS", 2)
    assert asyncio.run(plugin_api.notify("ext_demo", roles=["all"], title="Broadcast"))["recipients"] == 2


def test_notify_respects_the_persons_category_setting(client, make_plugin):
    make_plugin()
    headers, uid = _person(client, "ext_n_off")
    with SessionLocal() as db:
        db.add(NotificationPreference(user_id=uid, category="plugins", enabled=False))
        db.commit()
    try:
        asyncio.run(plugin_api.notify("ext_demo", user_ids=[uid], title="Muted"))
        assert _log(uid)[-1].suppressed is True  # in the history, but no push
    finally:
        with SessionLocal() as db:
            db.query(NotificationPreference).filter(NotificationPreference.user_id == uid).delete()
            db.commit()


def test_category_plugins_can_be_saved_in_notification_settings(client):
    headers, _ = _person(client, "ext_n_set")
    r = client.put("/api/push/me/notification-prefs", headers=headers, json=[{"category": "plugins", "enabled": False}])
    assert r.status_code == 200
    prefs = client.get("/api/push/me/notification-prefs", headers=headers).json()
    assert any(p["category"] == "plugins" and p["enabled"] is False for p in prefs)


def test_notify_is_rate_limited_per_plugin(client, make_plugin, monkeypatch):
    make_plugin("ext_a"), make_plugin("ext_b")
    _, uid = _person(client, "ext_n_rate")
    monkeypatch.setattr(plugin_api, "RATE_LIMIT_PER_HOUR", 3)
    results = [asyncio.run(plugin_api.notify("ext_a", user_ids=[uid], title=f"n{i}")) for i in range(5)]
    assert [r["sent"] for r in results] == [True, True, True, False, False]
    assert results[3]["reason"] == "rate_limited"
    assert asyncio.run(plugin_api.notify("ext_b", user_ids=[uid], title="other plugin"))["sent"]  # own budget
    assert [e.title for e in _log(uid)][-4:] == ["n0", "n1", "n2", "other plugin"]
    # An hour later the budget is back
    plugin_api._sent["ext_a"].clear()  # noqa: SLF001
    assert asyncio.run(plugin_api.notify("ext_a", user_ids=[uid], title="later"))["sent"]


def test_notify_drops_unusable_requests(client, make_plugin, monkeypatch):
    plugin = make_plugin()
    _, uid = _person(client, "ext_n_drop")
    n = len(_log(uid))
    assert asyncio.run(plugin_api.notify("nobody", user_ids=[uid], title="x"))["reason"] == "inactive"
    assert asyncio.run(plugin_api.notify("ext_demo", title="no recipients"))["reason"] == "no_recipients"
    assert asyncio.run(plugin_api.notify("ext_demo", user_ids=[999999], title="unknown person"))["reason"] == "no_recipients"
    assert asyncio.run(plugin_api.notify("ext_demo", user_ids=[uid], title="   "))["reason"] == "invalid"
    monkeypatch.setattr(settings, "plugins_disabled", "ext_demo")
    assert asyncio.run(plugin_api.notify("ext_demo", user_ids=[uid], title="off"))["reason"] == "inactive"
    assert len(_log(uid)) == n and plugin.active is False


def test_notify_sanitises_text_and_data(client, make_plugin, monkeypatch):
    make_plugin()
    _, uid = _person(client, "ext_n_clean")
    seen = []

    async def record(user_id, title, body, data=None, category="info", source="hub", silent=False):
        seen.append((title, body, data, category, source))
        return 1

    monkeypatch.setattr("app.services.notify.notify", record)
    asyncio.run(plugin_api.notify(
        "ext_demo", user_ids=[uid], title="T" * 300, body="B" * 2000, url="http://insecure.example",
        data={"actions": "done,snooze_1h", "action_token": "x", "notification_id": 1, "route": "//evil.example",
              "ok": "yes", "nested": {"a": 1}, **{f"k{i}": "v" for i in range(30)}}))
    title, body, data, category, source = seen[0]
    assert len(title) <= plugin_api.MAX_TITLE and len(body) <= plugin_api.MAX_BODY
    assert "url" not in data and "route" not in data and data["ok"] == "yes" and "nested" not in data
    assert not {"actions", "action_token", "notification_id"} & set(data) and len(data) <= plugin_api.MAX_DATA_KEYS
    assert (category, source) == ("plugins", "plugin:ext_demo")
    asyncio.run(plugin_api.notify("ext_demo", user_ids=[uid], title="t", url="https://example.org/a"))
    assert seen[1][2]["url"] == "https://example.org/a"


def test_notify_never_raises(client, make_plugin, monkeypatch):
    make_plugin()
    _, uid = _person(client, "ext_n_err")

    async def broken(*a, **kw):
        raise RuntimeError("push service down")

    monkeypatch.setattr("app.services.notify.notify", broken)
    r = asyncio.run(plugin_api.notify("ext_demo", user_ids=[uid], title="x"))
    assert r["sent"] is True and r["delivered"] == 0


# --- Scheduled jobs ---

def test_job_runs_for_active_plugins_at_their_interval(make_plugin, monkeypatch):
    plugin = make_plugin()
    plugin.schedule_minutes = 10
    clock = [1000.0]
    monkeypatch.setattr(jobs.time, "monotonic", lambda: clock[0])
    assert asyncio.run(jobs.run_due(wait=True)) == ["ext_demo"] and plugin.job_calls == 1
    clock[0] += 9 * 60
    assert asyncio.run(jobs.run_due(wait=True)) == [] and plugin.job_calls == 1
    clock[0] += 61
    assert asyncio.run(jobs.run_due(wait=True)) == ["ext_demo"] and plugin.job_calls == 2


def test_interval_is_at_least_five_minutes(make_plugin, monkeypatch):
    plugin = make_plugin()
    plugin.schedule_minutes = 1
    assert jobs.interval_seconds(plugin) == 300
    clock = [0.0]
    monkeypatch.setattr(jobs.time, "monotonic", lambda: clock[0])
    asyncio.run(jobs.run_due(wait=True))
    clock[0] = 240
    assert asyncio.run(jobs.run_due(wait=True)) == []
    clock[0] = 301
    assert asyncio.run(jobs.run_due(wait=True)) == ["ext_demo"]


@pytest.mark.parametrize("minutes", [None, 0, -5, "10", True])
def test_no_valid_schedule_no_job(make_plugin, minutes):
    plugin = make_plugin()
    plugin.schedule_minutes = minutes
    assert asyncio.run(jobs.run_due(wait=True)) == [] and plugin.job_calls == 0


def test_schedule_can_be_a_class_attribute():
    class Sub(Plugin):
        schedule_minutes = 15

        def __init__(self):
            super().__init__(id="ext_sub", name="Sub")

    assert Sub().schedule_minutes == 15 and Plugin(id="x", name="x").schedule_minutes is None


def test_failing_job_is_logged_and_does_not_stop_others(make_plugin):
    bad, good = make_plugin("ext_bad"), make_plugin("ext_good")
    bad.schedule_minutes = good.schedule_minutes = 5

    async def boom(db):
        raise RuntimeError("secret-token-123")

    bad.job = boom
    from app.core import log_buffer

    assert sorted(asyncio.run(jobs.run_due(wait=True))) == ["ext_bad", "ext_good"]
    assert good.job_calls == 1 and bad.job_calls == 1
    text = " ".join(e["message"] for e in log_buffer.entries())
    assert "ext_bad: scheduled job failed: RuntimeError" in text and "secret-token-123" not in text


def test_slow_job_is_stopped_and_jobs_never_overlap(make_plugin, monkeypatch):
    plugin = make_plugin()
    plugin.schedule_minutes = 5
    monkeypatch.setattr(jobs, "SCHEDULED_TIMEOUT", 0.2)
    started = []

    async def hang(db):
        started.append(1)
        await asyncio.sleep(30)

    plugin.job = hang

    async def scenario():
        first = await jobs.run_due()  # does not wait for the job
        again = await jobs.run_due()  # still running: not started a second time
        assert first == ["ext_demo"] and again == [] and "ext_demo" in jobs._running  # noqa: SLF001
        await asyncio.wait_for(asyncio.gather(*jobs._running.values()), 5)  # noqa: SLF001
        return jobs._running  # noqa: SLF001

    assert asyncio.run(scenario()) == {} and started == [1]


def test_job_gets_a_database_session(make_plugin):
    plugin = make_plugin()
    plugin.schedule_minutes = 5
    counted = []

    async def job(db):
        counted.append(db.query(User).count())

    plugin.job = job
    asyncio.run(jobs.run_due(wait=True))
    assert counted and counted[0] >= 0


def test_scheduler_loop_starts_plugin_jobs_and_survives_their_failure(monkeypatch):
    from app.services import scheduler

    calls = []

    async def run_due():
        calls.append(1)
        raise RuntimeError("plugin system broke")

    async def fast_sleep(_):
        if len(calls) >= 2:
            raise asyncio.CancelledError
    monkeypatch.setattr("app.plugins.jobs.run_due", run_due)
    monkeypatch.setattr(scheduler.asyncio, "sleep", fast_sleep)

    async def tick():
        return None

    monkeypatch.setattr(scheduler, "_tick", tick)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(scheduler.run_scheduler())
    assert len(calls) == 2  # the loop went on after the first failure


# --- Connection test ---

def test_admin_test_uses_the_plugins_own_test_with_stored_secrets(client, auth, make_plugin, monkeypatch):
    plugin = make_plugin("ext_conn", settings=(Setting("EXT_CONN_URL", "Address", required=False),
                                               Setting("EXT_CONN_TOKEN", "Token", secret=True, required=False)))
    monkeypatch.setenv("EXT_CONN_TOKEN", "stored-token")
    seen = []

    async def test(values):
        seen.append(values)
        return {"ok": values["EXT_CONN_TOKEN"] == "stored-token", "level": "weird", "message": "Checked " + values["EXT_CONN_URL"]}

    plugin.test = test
    assert plugin.has_test and plugin.describe()["has_test"] is True
    r = client.post("/api/admin/plugins/ext_conn/test", headers=auth,
                    json={"values": {"EXT_CONN_URL": "https://x.example", "EXT_CONN_TOKEN": ""}})
    assert r.json() == {"ok": True, "level": "ok", "message": "Checked https://x.example"}
    assert seen == [{"EXT_CONN_URL": "https://x.example", "EXT_CONN_TOKEN": "stored-token"}]  # empty secret = stored
    r = client.post("/api/admin/plugins/ext_conn/test", headers=auth,
                    json={"values": {"EXT_CONN_URL": "https://x.example", "EXT_CONN_TOKEN": "typed"}})
    assert r.json()["ok"] is False and r.json()["level"] == "error"  # typed value wins over the stored one
    assert client.post("/api/admin/plugins/ext_conn/test", headers=auth,
                       json={"values": {"OTHER": "x"}}).status_code == 422


def test_admin_test_survives_a_failing_or_slow_test(client, auth, make_plugin, monkeypatch):
    plugin = make_plugin("ext_conn2", settings=(Setting("EXT_CONN2_URL", "Address", required=False),))

    async def boom(values):
        raise RuntimeError("token abc leaked")

    plugin.test = boom
    r = client.post("/api/admin/plugins/ext_conn2/test", headers=auth, json={"values": {}})
    assert r.status_code == 200 and r.json()["ok"] is False and "abc" not in r.text

    async def hang(values):
        await asyncio.sleep(30)

    plugin.test = hang
    monkeypatch.setattr(hooks, "TEST_SETTINGS_TIMEOUT", 0.2)
    assert client.post("/api/admin/plugins/ext_conn2/test", headers=auth, json={"values": {}}).json()["ok"] is False

    async def junk(values):
        return "fine"

    plugin.test = junk
    assert client.post("/api/admin/plugins/ext_conn2/test", headers=auth, json={"values": {}}).json()["ok"] is False


def test_plugin_without_own_test_keeps_the_generic_check():
    plugin = Plugin(id="ext_plain", name="Plain")
    assert plugin.has_test is False and plugin.describe()["has_test"] is False
    assert asyncio.run(plugin.test_settings({})) is None
