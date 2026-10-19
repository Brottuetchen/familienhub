"""Kids mode: stars for tasks and rewards (#17)."""

import threading

import pytest

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User


def _login(client, name, role):
    with SessionLocal() as db:
        if not db.query(User).filter(User.username == name).first():
            db.add(User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"),
                        role=role, full_name=name.title()))
            db.commit()
        uid = db.query(User).filter(User.username == name).first().id
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}, uid


@pytest.fixture()
def fam(client):
    mom, mom_id = _login(client, "st_mom", "partner")
    kid, kid_id = _login(client, "st_kid", "child")
    kid2, kid2_id = _login(client, "st_kid2", "child")
    client.put("/api/stars/settings", headers=mom, json={"confirm_tasks": False})
    return {"mom": mom, "mom_id": mom_id, "kid": kid, "kid_id": kid_id, "kid2": kid2, "kid2_id": kid2_id}


def _hub_task(client, fam, stars, who="kid", title="Zimmer aufräumen"):
    account = f"{fam['mom_id']}:hub"
    r = client.post("/api/tasks", params={"provider": "hub_tasks", "account": account}, headers=fam["mom"],
                    json={"title": title, "assignee_id": fam[f"{who}_id"], "stars": stars})
    assert r.status_code == 201, r.text
    assert r.json()["stars"] == stars
    return r.json()["uid"]


def _complete(client, fam, uid, who="kid"):
    return client.post(f"/api/tasks/{uid}/complete",
                       params={"provider": "hub_tasks", "account": f"{fam[f'{who}_id']}:hub"}, headers=fam[who])


def _balance(client, fam, who="kid"):
    return client.get("/api/stars/me", headers=fam[who]).json()


def _reward(client, fam, price, title="30 Minuten Medienzeit"):
    r = client.post("/api/stars/rewards", headers=fam["mom"], json={"title": title, "price": price})
    assert r.status_code == 201
    return r.json()["id"]


def test_completing_a_starred_task_pays_the_completer_once(client, fam):
    before = _balance(client, fam)["balance"]
    uid = _hub_task(client, fam, 5)
    r = _complete(client, fam, uid)
    assert r.status_code == 200 and r.json()["stars_awarded"]["stars"] == 5
    again = _complete(client, fam, uid)
    assert again.status_code == 200 and "stars_awarded" not in again.json()
    assert _balance(client, fam)["balance"] == before + 5
    assert _balance(client, fam, "kid2")["balance"] == 0


def test_tasks_list_shows_stars(client, fam):
    uid = _hub_task(client, fam, 3, title="Müll rausbringen")
    items = client.get("/api/tasks", params={"provider": "hub_tasks", "view": "mine",
                                             "account": f"{fam['kid_id']}:hub"}, headers=fam["kid"]).json()["items"]
    assert [t["stars"] for t in items if t["uid"] == uid] == [3]


def test_stars_work_for_any_provider_key(client, fam):
    """External sources: stars are stored hub-side by provider and uid."""
    r = client.put("/api/stars/tasks/nextcloud/ext-uid-1", headers=fam["mom"], json={"stars": 4})
    assert r.status_code == 200 and r.json()["stars"] == 4
    assert client.put("/api/stars/tasks/nextcloud/ext-uid-1", headers=fam["mom"], json={"stars": 0}).json()["stars"] == 0
    assert client.put("/api/stars/tasks/habitica/x", headers=fam["mom"], json={"stars": 1}).status_code == 422


def test_child_cannot_grant_or_manage(client, fam):
    kid = fam["kid"]
    assert client.put("/api/stars/tasks/hub_tasks/abc", headers=kid, json={"stars": 50}).status_code == 403
    assert client.post("/api/stars/rewards", headers=kid, json={"title": "x", "price": 1}).status_code == 403
    assert client.post("/api/stars/adjust", headers=kid, json={"user_id": fam["kid_id"], "delta": 10}).status_code == 403
    assert client.put("/api/stars/settings", headers=kid, json={"confirm_tasks": False}).status_code == 403
    assert client.post("/api/stars/requests/1/approve", headers=kid).status_code == 403
    assert client.post("/api/stars/ledger/1/confirm", headers=kid).status_code == 403
    assert client.get("/api/stars/pending", headers=kid).status_code == 403
    assert client.post("/api/tasks", params={"provider": "hub_tasks", "account": f"{fam['kid_id']}:hub"},
                       headers=kid, json={"title": "Selbst", "stars": 99}).status_code == 403
    assert client.get("/api/stars/ledger", params={"user_id": fam["kid2_id"]}, headers=kid).status_code == 403


def test_reward_request_approve_flow_and_history(client, fam):
    kid, mom = fam["kid"], fam["mom"]
    client.post("/api/stars/adjust", headers=mom, json={"user_id": fam["kid_id"], "delta": 40, "title": "Start"})
    start = _balance(client, fam)
    reward = _reward(client, fam, 30)
    r = client.post("/api/stars/requests", headers=kid, json={"reward_id": reward})
    assert r.status_code == 201
    req = r.json()["id"]
    mid = _balance(client, fam)
    assert mid["balance"] == start["balance"] and mid["available"] == start["available"] - 30
    assert client.get("/api/stars/pending", headers=mom).json()["requests"][0]["id"] == req
    assert client.post(f"/api/stars/requests/{req}/approve", headers=mom).status_code == 200
    end = _balance(client, fam)
    assert end["balance"] == start["balance"] - 30 and end["reserved"] == 0
    assert client.post(f"/api/stars/requests/{req}/approve", headers=mom).status_code == 409
    assert client.post(f"/api/stars/requests/{req}/decline", headers=mom).status_code == 409
    hist = client.get("/api/stars/ledger", params={"user_id": fam["kid_id"]}, headers=mom).json()["items"]
    assert hist[0]["kind"] == "reward" and hist[0]["delta"] == -30


def test_declined_and_cancelled_requests_release_the_reservation(client, fam):
    kid, mom = fam["kid"], fam["mom"]
    client.post("/api/stars/adjust", headers=mom, json={"user_id": fam["kid_id"], "delta": 20})
    start = _balance(client, fam)["available"]
    reward = _reward(client, fam, 10)
    a = client.post("/api/stars/requests", headers=kid, json={"reward_id": reward}).json()["id"]
    b = client.post("/api/stars/requests", headers=kid, json={"reward_id": reward}).json()["id"]
    assert _balance(client, fam)["available"] == start - 20
    assert client.post(f"/api/stars/requests/{a}/decline", headers=mom).status_code == 200
    assert client.post(f"/api/stars/requests/{b}/cancel", headers=kid).status_code == 200
    assert client.post(f"/api/stars/requests/{b}/cancel", headers=kid).status_code == 409
    after = _balance(client, fam)
    assert after["available"] == start and after["reserved"] == 0
    other = client.post("/api/stars/requests", headers=kid, json={"reward_id": reward}).json()["id"]
    assert client.post(f"/api/stars/requests/{other}/cancel", headers=fam["kid2"]).status_code == 404
    client.post(f"/api/stars/requests/{other}/cancel", headers=kid)


def test_balance_never_negative(client, fam):
    kid, mom = fam["kid"], fam["mom"]
    available = _balance(client, fam)["available"]
    dear = _reward(client, fam, available + 1000, "Pony")
    assert client.post("/api/stars/requests", headers=kid, json={"reward_id": dear}).status_code == 409
    assert client.post("/api/stars/adjust", headers=mom,
                       json={"user_id": fam["kid_id"], "delta": -(available + 1)}).status_code == 409
    assert _balance(client, fam)["balance"] >= 0
    assert client.post("/api/stars/requests", headers=kid, json={"reward_id": 99999}).status_code == 404


def test_concurrent_requests_cannot_overspend(client, fam):
    mom, kid2 = fam["mom"], fam["kid2"]
    client.post("/api/stars/adjust", headers=mom, json={"user_id": fam["kid2_id"], "delta": 10})
    reward = _reward(client, fam, 10, "Eis")
    avail = _balance(client, fam, "kid2")["available"]
    codes, gate = [], threading.Barrier(6)

    def go():
        gate.wait()
        codes.append(client.post("/api/stars/requests", headers=kid2, json={"reward_id": reward}).status_code)

    threads = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert codes.count(201) == avail // 10
    after = _balance(client, fam, "kid2")
    assert 0 <= after["reserved"] <= after["balance"]


def test_concurrent_approvals_book_once(client, fam):
    mom = fam["mom"]
    client.post("/api/stars/adjust", headers=mom, json={"user_id": fam["kid_id"], "delta": 10})
    reward = _reward(client, fam, 10, "Kino")
    req = client.post("/api/stars/requests", headers=fam["kid"], json={"reward_id": reward}).json()["id"]
    before = _balance(client, fam)["balance"]
    codes, gate = [], threading.Barrier(4)

    def go():
        gate.wait()
        codes.append(client.post(f"/api/stars/requests/{req}/approve", headers=mom).status_code)

    threads = [threading.Thread(target=go) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert codes.count(200) == 1 and codes.count(409) == 3
    assert _balance(client, fam)["balance"] == before - 10


def test_confirmation_mode_holds_stars_until_a_parent_confirms(client, fam):
    mom = fam["mom"]
    assert client.put("/api/stars/settings", headers=mom, json={"confirm_tasks": True}).json() == {"confirm_tasks": True}
    try:
        before = _balance(client, fam)["balance"]
        uid = _hub_task(client, fam, 7, title="Hausaufgaben")
        done = _complete(client, fam, uid).json()["stars_awarded"]
        assert done["status"] == "pending"
        assert _balance(client, fam)["balance"] == before
        entry = [a for a in client.get("/api/stars/pending", headers=mom).json()["awards"] if a["id"] == done["ledger_id"]]
        assert entry and entry[0]["user_name"]
        assert client.post(f"/api/stars/ledger/{done['ledger_id']}/confirm", headers=fam["kid"]).status_code == 403
        assert client.post(f"/api/stars/ledger/{done['ledger_id']}/confirm", headers=mom).status_code == 200
        assert client.post(f"/api/stars/ledger/{done['ledger_id']}/confirm", headers=mom).status_code == 409
        assert client.post(f"/api/stars/ledger/{done['ledger_id']}/reject", headers=mom).status_code == 409
        assert _balance(client, fam)["balance"] == before + 7

        uid = _hub_task(client, fam, 9, title="Fenster putzen")
        rejected = _complete(client, fam, uid).json()["stars_awarded"]
        assert client.post(f"/api/stars/ledger/{rejected['ledger_id']}/reject", headers=mom).status_code == 200
        assert _balance(client, fam)["balance"] == before + 7
    finally:
        client.put("/api/stars/settings", headers=mom, json={"confirm_tasks": False})


def test_parents_own_completions_are_not_held(client, fam):
    mom = fam["mom"]
    client.put("/api/stars/settings", headers=mom, json={"confirm_tasks": True})
    try:
        uid = _hub_task(client, fam, 2, who="mom", title="Steuer")
        r = _complete(client, fam, uid, "mom")
        assert r.json()["stars_awarded"]["status"] == "confirmed"
    finally:
        client.put("/api/stars/settings", headers=mom, json={"confirm_tasks": False})


def test_parents_cannot_decide_on_their_own_requests_or_stars(client, fam):
    mom = fam["mom"]
    assert client.post("/api/stars/adjust", headers=mom, json={"user_id": fam["mom_id"], "delta": 5}).status_code == 403
    client.post("/api/stars/adjust", headers=mom, json={"user_id": fam["kid_id"], "delta": 1})


def test_today_card_data_and_layout(client, fam):
    mom, kid = fam["mom"], fam["kid"]
    _reward(client, fam, 500, "Ausflug")
    me = _balance(client, fam)
    assert me["enabled"] and me["next_reward"]["price"] >= me["available"] or me["next_reward"]["missing"] == 0
    assert "pending" in client.get("/api/stars/me", headers=mom).json()
    assert [c["id"] for c in client.get("/api/me/today-layout", headers=kid).json()["cards"]][-1] == "stars"
    guest, _ = _login(client, "st_guest", "guest")
    assert client.get("/api/stars/me", headers=guest).json()["enabled"] is False


def test_person_without_use_has_no_card(client, fam):
    lonely, _ = _login(client, "st_adult", "partner")
    body = client.get("/api/stars/me", headers=lonely).json()
    assert body["balance"] == 0 and body["enabled"] is False or body["pending"]["total"] > 0


def test_rotation_successor_keeps_the_stars(client, fam):
    mom = fam["mom"]
    r = client.post("/api/tasks", params={"provider": "hub_tasks", "account": f"{fam['mom_id']}:hub"}, headers=mom,
                    json={"title": "Bad putzen", "list": "family", "recurrence": "weekly", "due": "2026-11-01",
                          "rotation": [fam["kid_id"], fam["kid2_id"]], "stars": 6})
    assert r.status_code == 201, r.text
    assert _complete(client, fam, r.json()["uid"]).json()["stars_awarded"]["stars"] == 6
    items = client.get("/api/tasks", params={"provider": "hub_tasks", "view": "family",
                                             "account": f"{fam['kid2_id']}:hub"}, headers=fam["kid2"]).json()["items"]
    assert [t["stars"] for t in items if t["title"] == "Bad putzen"] == [6]
