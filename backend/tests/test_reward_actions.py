"""Reward actions (kids mode): a plugin action runs after a parent approves a reward (docs/plugins.md)."""

import asyncio

import pytest

from app.config import settings
from app.core import log_buffer
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.notification_log import NotificationLog
from app.models.stars import StarReward
from app.models.user import User
from app.plugins import Plugin, Setting, hooks
from app.plugins.registry import plugin_registry

SPECS = [{"id": "unlock", "label": "Unlock the tablet", "params": [
    {"key": "minutes", "label": "Minutes", "type": "number", "required": True},
    {"key": "device", "label": "Device", "type": "select", "options": [{"value": "tab", "label": "Tablet"}, "tv"],
     "default": "tab"},
    {"key": "note", "label": "Note", "type": "text", "required": False},
    {"key": "loud", "label": "Loud", "type": "bool"},
]}, {"id": "ping", "label": "Just ping"}, {"id": "bad id!", "label": "x"}, {"label": "no id"}, "junk"]


class Rewarder(Plugin):
    def __init__(self, pid="kidsync", **kw):
        super().__init__(id=pid, name="Kid sync", **kw)
        self.calls = []
        self.result = {"ok": True, "message": "Tablet unlocked for 30 min"}

    def reward_actions(self):
        return SPECS

    async def run_reward_action(self, action_id, params, child, reward, db):
        self.calls.append((action_id, dict(params), child.username, reward.title))
        if isinstance(self.result, Exception):
            raise self.result
        if callable(self.result):
            return await self.result()
        return self.result


@pytest.fixture
def plugin():
    p = Rewarder()
    plugin_registry.register(p)
    yield p
    plugin_registry.unregister(p.id)


def _login(client, name, role):
    with SessionLocal() as db:
        if not db.query(User).filter(User.username == name).first():
            db.add(User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"),
                        role=role, full_name=name.title()))
            db.commit()
        uid = db.query(User).filter(User.username == name).first().id
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}, uid


@pytest.fixture
def fam(client):
    mom, mom_id = _login(client, "ra_mom", "partner")
    kid, kid_id = _login(client, "ra_kid", "child")
    client.post("/api/stars/adjust", headers=mom, json={"user_id": kid_id, "delta": 500, "title": "start"})
    return {"mom": mom, "mom_id": mom_id, "kid": kid, "kid_id": kid_id}


ACTION = {"plugin": "kidsync", "action": "unlock", "params": {"minutes": 30}}


def _reward(client, fam, action=ACTION, title="Tablet time", price=1):
    r = client.post("/api/stars/rewards", headers=fam["mom"], json={"title": title, "price": price, "action": action})
    assert r.status_code == 201, r.text
    return r.json()


def _approve(client, fam, reward_id):
    req = client.post("/api/stars/requests", headers=fam["kid"], json={"reward_id": reward_id})
    assert req.status_code == 201, req.text
    return req.json()["id"], client.post(f"/api/stars/requests/{req.json()['id']}/approve", headers=fam["mom"])


def _notes(uid):
    with SessionLocal() as db:
        return [(n.title, n.body) for n in db.query(NotificationLog).filter(NotificationLog.user_id == uid)
                .order_by(NotificationLog.id)]


# --- Which actions exist ---

def test_actions_of_active_plugins_are_listed_sanitised(client, fam, plugin):
    items = client.get("/api/stars/reward-actions", headers=fam["mom"]).json()["items"]
    mine = [i for i in items if i["plugin"] == "kidsync"]
    assert [i["id"] for i in mine] == ["unlock", "ping"]  # the malformed entries are gone
    unlock = mine[0]
    assert unlock["plugin_name"] == "Kid sync" and unlock["label"] == "Unlock the tablet"
    params = {p["key"]: p for p in unlock["params"]}
    assert params["minutes"]["required"] is True and params["note"]["required"] is False
    assert params["loud"]["required"] is False  # a switch is never required
    assert params["device"]["options"] == [{"value": "tab", "label": "Tablet"}, {"value": "tv", "label": "tv"}]
    assert mine[1]["params"] == []


def test_only_parents_see_the_choices_and_the_attached_action(client, fam, plugin):
    assert client.get("/api/stars/reward-actions", headers=fam["kid"]).status_code == 403
    _reward(client, fam)
    kid_view = client.get("/api/stars/rewards", headers=fam["kid"]).json()["items"]
    assert kid_view and all("action" not in r for r in kid_view)
    mom_view = [r for r in client.get("/api/stars/rewards", headers=fam["mom"]).json()["items"] if r["action"]]
    assert mom_view[0]["action"] == {"plugin": "kidsync", "action": "unlock", "available": True,
                                     "label": "Unlock the tablet", "plugin_name": "Kid sync",
                                     "params": {"minutes": "30", "device": "tab", "loud": "false"}}


def test_inactive_plugins_offer_nothing(client, fam, monkeypatch):
    p = Rewarder("kidsync2", settings=(Setting("KIDSYNC2_URL", "Address"),))  # required setting missing
    plugin_registry.register(p)
    try:
        assert not any(i["plugin"] == "kidsync2" for i in client.get("/api/stars/reward-actions",
                                                                       headers=fam["mom"]).json()["items"])
        r = client.post("/api/stars/rewards", headers=fam["mom"], json={
            "title": "x", "price": 1, "action": {"plugin": "kidsync2", "action": "ping"}})
        assert r.status_code == 422
    finally:
        plugin_registry.unregister("kidsync2")


# --- Creating and editing ---

@pytest.mark.parametrize("action, why", [
    ({"plugin": "kidsync", "action": "nope"}, "unknown action"),
    ({"plugin": "nobody", "action": "unlock", "params": {"minutes": 1}}, "unknown plugin"),
    ({"plugin": "kidsync", "action": "unlock", "params": {}}, "required param missing"),
    ({"plugin": "kidsync", "action": "unlock", "params": {"minutes": "abc"}}, "not a number"),
    ({"plugin": "kidsync", "action": "unlock", "params": {"minutes": 5, "device": "fridge"}}, "not an option"),
    ({"plugin": "kidsync", "action": "unlock", "params": {"minutes": 5, "extra": 1}}, "unknown param"),
    ({"plugin": "kidsync", "action": "unlock", "params": {"minutes": 5, "note": "a\nb"}}, "line break"),
    ({"plugin": "kidsync", "action": "unlock", "params": {"minutes": 5, "note": "x" * 400}}, "too long"),
])
def test_invalid_actions_are_refused_and_leave_no_reward(client, fam, plugin, action, why):
    before = len(client.get("/api/stars/rewards", headers=fam["mom"]).json()["items"])
    r = client.post("/api/stars/rewards", headers=fam["mom"], json={"title": "T", "price": 3, "action": action})
    assert r.status_code == 422, why
    assert len(client.get("/api/stars/rewards", headers=fam["mom"]).json()["items"]) == before


def test_children_cannot_create_rewards_with_actions(client, fam, plugin):
    r = client.post("/api/stars/rewards", headers=fam["kid"], json={"title": "T", "price": 1, "action": ACTION})
    assert r.status_code == 403


def test_edit_changes_and_removes_the_action(client, fam, plugin):
    reward = _reward(client, fam)
    new = {"plugin": "kidsync", "action": "ping"}
    r = client.patch(f"/api/stars/rewards/{reward['id']}", headers=fam["mom"], json={"action": new})
    assert r.json()["action"]["action"] == "ping" and r.json()["action"]["params"] == {}
    r = client.patch(f"/api/stars/rewards/{reward['id']}", headers=fam["mom"], json={"price": 2})
    assert r.json()["action"]["action"] == "ping"  # left out = unchanged
    assert client.patch(f"/api/stars/rewards/{reward['id']}", headers=fam["mom"],
                        json={"action": {"plugin": "kidsync", "action": "zzz"}}).status_code == 422
    r = client.patch(f"/api/stars/rewards/{reward['id']}", headers=fam["mom"], json={"action": None})
    assert r.json()["action"] is None
    with SessionLocal() as db:
        row = db.get(StarReward, reward["id"])
        assert (row.action_plugin, row.action_id, row.action_params) == (None, None, None)


def test_reward_without_action_is_unchanged(client, fam):
    r = client.post("/api/stars/rewards", headers=fam["mom"], json={"title": "Ice cream", "price": 1})
    assert r.status_code == 201 and r.json()["action"] is None
    rid, approve = _approve(client, fam, r.json()["id"])
    assert approve.status_code == 200 and "action_result" not in approve.json()


# --- Running on approval ---

def test_approval_runs_the_action_and_tells_both(client, fam, plugin):
    reward = _reward(client, fam, action={**ACTION, "params": {"minutes": 30, "note": "Weekend"}})
    balance = client.get("/api/stars/me", headers=fam["kid"]).json()["balance"]
    mom_before, kid_before = len(_notes(fam["mom_id"])), len(_notes(fam["kid_id"]))
    _, r = _approve(client, fam, reward["id"])
    body = r.json()
    assert r.status_code == 200 and body["status"] == "approved"
    assert body["action_result"] == {"plugin": "kidsync", "action": "unlock", "ok": True,
                                     "message": "Tablet unlocked for 30 min"}
    assert plugin.calls == [("unlock", {"minutes": "30", "device": "tab", "note": "Weekend", "loud": "false"},
                             "ra_kid", "Tablet time")]
    assert client.get("/api/stars/me", headers=fam["kid"]).json()["balance"] == balance - 1
    assert ("Belohnungs-Aktion ausgeführt", "Tablet time: Tablet unlocked for 30 min") in _notes(fam["mom_id"])[mom_before:]
    assert ("Belohnung eingelöst", "Tablet time: Tablet unlocked for 30 min") in _notes(fam["kid_id"])[kid_before:]


def test_action_runs_once_and_not_on_decline_or_cancel(client, fam, plugin):
    reward = _reward(client, fam)
    rid, first = _approve(client, fam, reward["id"])
    again = client.post(f"/api/stars/requests/{rid}/approve", headers=fam["mom"])
    assert again.status_code == 409 and len(plugin.calls) == 1
    req = client.post("/api/stars/requests", headers=fam["kid"], json={"reward_id": reward["id"]}).json()
    assert client.post(f"/api/stars/requests/{req['id']}/decline", headers=fam["mom"]).status_code == 200
    req = client.post("/api/stars/requests", headers=fam["kid"], json={"reward_id": reward["id"]}).json()
    assert client.post(f"/api/stars/requests/{req['id']}/cancel", headers=fam["kid"]).status_code == 200
    assert len(plugin.calls) == 1


@pytest.mark.parametrize("result", [
    {"ok": False, "message": "Tablet not reachable"},
    RuntimeError("token-xyz leaked"),
    "not a dict",
    None,
])
def test_a_failing_action_never_reverts_the_approval(client, fam, plugin, result):
    plugin.result = result
    reward = _reward(client, fam)
    balance = client.get("/api/stars/me", headers=fam["kid"]).json()["balance"]
    mom_before, kid_before = len(_notes(fam["mom_id"])), len(_notes(fam["kid_id"]))
    rid, r = _approve(client, fam, reward["id"])
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert r.json()["action_result"]["ok"] is False and "token-xyz" not in r.text
    assert client.get("/api/stars/me", headers=fam["kid"]).json()["balance"] == balance - 1  # stars were paid
    again = client.get("/api/stars/requests", headers=fam["mom"], params={"status": "approved"}).json()["items"]
    assert any(i["id"] == rid for i in again)
    titles_mom = [t for t, _ in _notes(fam["mom_id"])[mom_before:]]
    assert "Belohnungs-Aktion fehlgeschlagen" in titles_mom
    assert not [t for t, _ in _notes(fam["kid_id"])[kid_before:] if t == "Belohnung eingelöst"]  # child only on success
    assert "token-xyz" not in " ".join(e["message"] for e in log_buffer.entries())


def test_plugin_failure_message_is_shown_to_the_parent(client, fam, plugin):
    plugin.result = {"ok": False, "message": "Tablet not reachable"}
    reward = _reward(client, fam)
    mom_before = len(_notes(fam["mom_id"]))
    _, r = _approve(client, fam, reward["id"])
    assert r.json()["action_result"]["message"] == "Tablet not reachable"
    assert ("Belohnungs-Aktion fehlgeschlagen", "Tablet time: Tablet not reachable") in _notes(fam["mom_id"])[mom_before:]


def test_a_slow_action_is_stopped(client, fam, plugin, monkeypatch):
    async def hang():
        await asyncio.sleep(30)

    plugin.result = hang
    monkeypatch.setattr("app.services.reward_actions.REWARD_ACTION_TIMEOUT", 0.2)
    reward = _reward(client, fam)
    _, r = _approve(client, fam, reward["id"])
    assert r.status_code == 200 and r.json()["status"] == "approved" and r.json()["action_result"]["ok"] is False


def test_plugin_switched_off_before_approval(client, fam, plugin, monkeypatch):
    reward = _reward(client, fam)
    req = client.post("/api/stars/requests", headers=fam["kid"], json={"reward_id": reward["id"]}).json()
    monkeypatch.setattr(settings, "plugins_disabled", "kidsync")
    mom_before = len(_notes(fam["mom_id"]))
    r = client.post(f"/api/stars/requests/{req['id']}/approve", headers=fam["mom"])
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert r.json()["action_result"]["ok"] is False and plugin.calls == []
    assert "Belohnungs-Aktion fehlgeschlagen" in [t for t, _ in _notes(fam["mom_id"])[mom_before:]]
    shown = [x for x in client.get("/api/stars/rewards", headers=fam["mom"]).json()["items"] if x["id"] == reward["id"]]
    assert shown[0]["action"]["available"] is False  # the parent sees that it cannot run right now


def test_plugin_removed_before_approval(client, fam, plugin):
    reward = _reward(client, fam)
    req = client.post("/api/stars/requests", headers=fam["kid"], json={"reward_id": reward["id"]}).json()
    plugin_registry.unregister("kidsync")
    r = client.post(f"/api/stars/requests/{req['id']}/approve", headers=fam["mom"])
    assert r.status_code == 200 and r.json()["status"] == "approved" and r.json()["action_result"]["ok"] is False


def test_removed_reward_row_means_no_action(client, fam, plugin):
    reward = _reward(client, fam)
    req = client.post("/api/stars/requests", headers=fam["kid"], json={"reward_id": reward["id"]}).json()
    client.delete(f"/api/stars/rewards/{reward['id']}", headers=fam["mom"])  # switched off, still there
    r = client.post(f"/api/stars/requests/{req['id']}/approve", headers=fam["mom"])
    assert r.status_code == 200 and r.json()["action_result"]["ok"] is True  # the request was made before


def test_action_result_text_is_sanitised():
    assert hooks.sanitize_result({"ok": True, "message": "x" * 900})["message"].endswith("…")
    assert hooks.sanitize_result({"ok": "yes", "message": "m"})["ok"] is False
    assert hooks.sanitize_result({"ok": True})["message"] == "OK"
    assert hooks.sanitize_result(None)["ok"] is False


def test_migration_adds_the_columns(tmp_path, monkeypatch):
    from alembic import command
    from sqlalchemy import create_engine, inspect

    from app.core.database import _alembic_config

    url = f"sqlite:///{tmp_path}/m.db"
    monkeypatch.setattr(settings, "database_url", url)
    cfg = _alembic_config()

    def columns():
        engine = create_engine(url)
        try:
            return {c["name"] for c in inspect(engine).get_columns("star_rewards")}
        finally:
            engine.dispose()

    new = {"action_plugin", "action_id", "action_params"}
    command.upgrade(cfg, "f8a9b0c1d2e3")
    assert not new & columns()
    command.upgrade(cfg, "b0a1c2d3e4f5")
    assert new <= columns()
    command.downgrade(cfg, "f8a9b0c1d2e3")
    assert not new & columns()
