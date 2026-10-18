"""#38: a task for another person lands in the recipient's own task place (own account only)."""
import uuid
from unittest.mock import patch

import httpx
import pytest
import respx

from app.core.crypto import encrypt
from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.models.caldav import CalDAVAccount, TaskList
from app.models.habitica import HabiticaAccount
from app.models.hub import HubTask
from app.models.task_assignment import TaskAssignment
from app.models.user import User
from tests.test_household import HouseholdCalendar
from tests.test_tasks_caldav import FakeDAVClient, FakePrincipal

HABITICA = "https://habitica.example"
REMOTE_USER = "55555555-5555-4555-8555-555555555555"


def _user(name, role="partner"):
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == name).first()
        if not user:
            user = User(username=name, email=f"{name}@example.com", hashed_password="unused", role=role)
            db.add(user)
        user.task_place = None
        db.query(CalDAVAccount).filter(CalDAVAccount.user_id == user.id).delete()
        db.query(TaskList).filter(TaskList.user_id == user.id).delete()
        db.query(HabiticaAccount).filter(HabiticaAccount.user_id == user.id).delete()
        db.query(HubTask).filter((HubTask.created_by == user.id) | (HubTask.assignee_id == user.id)).delete()
        db.query(TaskAssignment).filter((TaskAssignment.creator_id == user.id) | (TaskAssignment.assignee_id == user.id)).delete()
        db.commit()
        db.refresh(user)
        return user.id, {"Authorization": f"Bearer {create_access_token({'sub': name})}"}


class World:
    """creator (Nextcloud + family list), mia (Nextcloud), const (Habitica), kid (hub only)."""

    def __init__(self, http):
        self.http = http
        self.sfx = uuid.uuid4().hex[:6]
        self.clients = {}
        self.calendars = {}
        self.creator, self.h_creator = _user("rt-creator")
        self.mia, self.h_mia = _user("rt-mia")
        self.const, self.h_leo = _user("rt-const")
        self.kid, self.h_kid = _user("rt-kid", role="child")
        self.remote_task = None  # Habitica remote object created for const
        with SessionLocal() as db:
            self._caldav(db, "rt-creator", self.creator, personal=True, family=True)
            self._caldav(db, "rt-mia", self.mia, personal=True)
            db.add(HabiticaAccount(user_id=self.const, server_url=HABITICA, remote_user_id=REMOTE_USER,
                                   api_key_enc=encrypt("rt-key")))
            db.commit()

    def _caldav(self, db, username, user_id, personal=False, family=False):
        visible = []
        db.add(CalDAVAccount(user_id=user_id, url="https://cloud.example/dav", username=username,
                             password_enc=encrypt("pw")))
        if personal:
            cal = HouseholdCalendar(f"{username}-personal-{self.sfx}", ["VTODO"])
            self.calendars[username] = cal
            visible.append(cal)
            db.add(TaskList(user_id=user_id, caldav_url=cal.url, display_name="Persönlich", kind="personal",
                            owner_user_id=user_id))
        if family:
            cal = HouseholdCalendar(f"{username}-family-{self.sfx}", ["VTODO"])
            self.calendars[f"{username}-family"] = cal
            visible.append(cal)
            db.add(TaskList(user_id=user_id, caldav_url=cal.url, display_name="Familie", kind="family"))
        fake = FakeDAVClient("https://cloud.example/dav", username, "pw")
        fake._principal = FakePrincipal(visible)
        self.clients[username] = fake

    def habitica_remote(self):
        """Habitica fake: POST creates the todo for the account, GET returns its current state."""
        def create(request):
            import json
            assert request.headers["x-api-user"] == REMOTE_USER  # the recipient's own credentials
            body = json.loads(request.content)
            self.remote_task = {"id": "66666666-6666-4666-8666-666666666666", "userId": REMOTE_USER, "type": "todo",
                                "text": body["text"], "notes": body.get("notes", ""), "completed": False,
                                "updatedAt": "v1"}
            return httpx.Response(200, json={"success": True, "data": self.remote_task})
        self.http.post(f"{HABITICA}/api/v3/tasks/user").mock(side_effect=create)
        self.http.route(method="GET", path__regex=r"/api/v3/tasks/66666666-.*").mock(
            side_effect=lambda r: httpx.Response(200, json={"success": True, "data": self.remote_task}))

    def create(self, headers, **payload):
        return self.http_client.post("/api/tasks?provider=auto", headers=headers, json={"title": "Müll", **payload})


@pytest.fixture()
def world(client, monkeypatch):
    monkeypatch.setenv("HABITICA_URL", HABITICA)
    monkeypatch.setenv("HABITICA_NATIVE_WRITE_ACCOUNTS", f"{HABITICA}|{REMOTE_USER}")
    monkeypatch.delenv("TASKS_SOURCES", raising=False)
    with respx.mock(using="httpx", assert_all_called=False) as http:
        http.route(host="testserver").pass_through()
        w = World(http)
        w.http_client = client
        with patch("caldav.DAVClient", side_effect=lambda **kw: w.clients[kw["username"]]):
            yield w


def _todos(cal):
    return list(cal._todos_data)


def _from_me(client, headers, done=True):
    r = client.get(f"/api/tasks?provider=all&view=from_me&include_done={'true' if done else 'false'}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# --- preferred place: derivation and API ---


def test_default_place_is_derived_from_connected_accounts(client, world):
    def place(h):
        return client.get("/api/tasks/me/place", headers=h).json()

    assert place(world.h_kid)["place"] == "hub_tasks" and place(world.h_kid)["explicit"] is None
    assert place(world.h_mia)["place"] == "nextcloud"
    assert place(world.h_leo)["place"] == "habitica"
    options = {o["id"]: o["available"] for o in place(world.h_mia)["options"]}
    assert options == {"nextcloud": True, "habitica": False, "hub_tasks": True}
    # Both connected: CalDAV wins by default
    with SessionLocal() as db:
        db.add(CalDAVAccount(user_id=world.const, url="https://cloud.example/dav", username="rt-creator",
                             password_enc=encrypt("pw")))
        db.commit()
    assert place(world.h_leo)["place"] == "nextcloud"


def test_place_can_be_chosen_and_reset(client, world):
    put = client.put("/api/tasks/me/place", headers=world.h_mia, json={"place": "hub_tasks"})
    assert put.status_code == 200 and put.json()["place"] == "hub_tasks" and put.json()["explicit"] == "hub_tasks"
    assert client.get("/api/tasks/me/place", headers=world.h_mia).json()["place"] == "hub_tasks"
    # a place she has no account for is refused
    assert client.put("/api/tasks/me/place", headers=world.h_mia, json={"place": "habitica"}).status_code == 422
    assert client.put("/api/tasks/me/place", headers=world.h_mia, json={"place": "nope"}).status_code == 422
    reset = client.put("/api/tasks/me/place", headers=world.h_mia, json={"place": None})
    assert reset.json()["place"] == "nextcloud" and reset.json()["explicit"] is None


def test_explicit_place_is_used_when_the_account_goes_away(client, world):
    client.put("/api/tasks/me/place", headers=world.h_leo, json={"place": "habitica"})
    with SessionLocal() as db:
        db.query(HabiticaAccount).filter(HabiticaAccount.user_id == world.const).delete()
        db.commit()
    info = client.get("/api/tasks/me/place", headers=world.h_leo).json()
    assert info["explicit"] == "habitica" and info["place"] == "hub_tasks"  # stale choice never blocks


# --- routing ---


def test_task_for_mia_lands_in_her_nextcloud_written_with_her_account(client, world):
    r = world.create(world.h_creator, assignee_id=world.mia, due="2099-01-02", notes="Tonne raus")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["placed"] == {"provider": "nextcloud", "fallback": False, "recipient": world.mia}
    assert body["provider"] == "assigned" and body["read_only"] is True and body["done"] is False
    mia_cal = world.calendars["rt-mia"]
    todo = _todos(mia_cal)
    assert len(todo) == 1 and "Müll" in todo[0]
    assert f"X-FAMILIENHUB-CREATED-BY:{world.creator}" in todo[0]
    assert f"X-FAMILIENHUB-ASSIGNEE:{world.mia}" in todo[0]
    assert _todos(world.calendars["rt-creator"]) == []  # the creator's own list and account stay untouched
    # Mia sees it under "for me"
    mine = client.get("/api/tasks?provider=nextcloud&view=for_me", headers=world.h_mia).json()["items"]
    assert [t["title"] for t in mine] == ["Müll"]


def test_von_mir_shows_the_task_and_follows_completion_by_the_recipient(client, world):
    created = world.create(world.h_creator, assignee_id=world.mia).json()
    items = _from_me(client, world.h_creator)["items"]
    assert [(t["title"], t["done"], t["via"]) for t in items] == [("Müll", False, "nextcloud")]
    done = client.post(f"/api/tasks/{created['uid']}/complete?provider=nextcloud", headers=world.h_mia)
    assert done.status_code == 200, done.text
    items = _from_me(client, world.h_creator)["items"]
    assert [(t["title"], t["done"], t["stale"]) for t in items] == [("Müll", True, False)]
    assert _from_me(client, world.h_creator, done=False)["items"] == []  # done tasks only with include_done


def test_creator_sees_only_the_tasks_he_assigned(client, world):
    # Mia's own task and one from the hub-less third person sit in the same list
    own = client.post("/api/tasks?provider=nextcloud", headers=world.h_mia, json={"title": "Privat von Mia"})
    assert own.status_code == 201
    other = client.post("/api/tasks?provider=auto", headers=world.h_leo,
                        json={"title": "Von Const", "assignee_id": world.mia})
    assert other.status_code == 201, other.text
    mine = world.create(world.h_creator, assignee_id=world.mia)
    assert mine.status_code == 201
    titles = [t["title"] for t in _from_me(client, world.h_creator)["items"]]
    assert titles == ["Müll"]


def test_task_for_const_goes_to_habitica_with_his_credentials(client, world):
    world.habitica_remote()
    r = world.create(world.h_creator, assignee_id=world.const, notes="Bitte bis Freitag")
    assert r.status_code == 201, r.text
    assert r.json()["placed"]["provider"] == "habitica" and r.json()["placed"]["fallback"] is False
    assert world.remote_task["text"] == "Müll"
    assert "Bitte bis Freitag" in world.remote_task["notes"] and "Von " in world.remote_task["notes"]
    assert [t["title"] for t in _from_me(client, world.h_creator)["items"]] == ["Müll"]
    assert _todos(world.calendars["rt-creator"]) == []
    # He ticks it off in Habitica; the creator's view follows
    world.remote_task["completed"] = True
    items = _from_me(client, world.h_creator)["items"]
    assert [(t["done"], t["via"]) for t in items] == [(True, "habitica")]


def test_task_for_kid_lands_in_the_hub(client, world):
    r = world.create(world.h_creator, assignee_id=world.kid, due="2099-01-02")
    assert r.status_code == 201, r.text
    assert r.json()["placed"] == {"provider": "hub_tasks", "fallback": False, "recipient": world.kid}
    assert r.json()["provider"] == "hub_tasks"  # the creator can open it like any hub task
    with SessionLocal() as db:
        t = db.query(HubTask).filter(HubTask.uid == r.json()["uid"]).one()
        assert (t.created_by, t.assignee_id, t.family) == (world.creator, world.kid, False)
    kid_tasks = client.get("/api/tasks?provider=hub_tasks&account=%d:hub&view=for_me" % world.kid,
                           headers=world.h_kid).json()["items"]
    assert [t["title"] for t in kid_tasks] == ["Müll"]
    items = _from_me(client, world.h_creator)["items"]
    assert [(t["title"], t["done"]) for t in items] == [("Müll", False)]  # once, not twice
    client.post(f"/api/tasks/{r.json()['uid']}/complete?provider=hub_tasks&account={world.kid}:hub", headers=world.h_kid)
    assert [t["done"] for t in _from_me(client, world.h_creator)["items"]] == [True]


def test_explicit_place_of_the_recipient_wins(client, world):
    client.put("/api/tasks/me/place", headers=world.h_mia, json={"place": "hub_tasks"})
    r = world.create(world.h_creator, assignee_id=world.mia)
    assert r.json()["placed"]["provider"] == "hub_tasks"
    assert _todos(world.calendars["rt-mia"]) == []


# --- fallback ---


def test_recipient_without_account_for_a_stale_choice_falls_back_to_hub(client, world):
    client.put("/api/tasks/me/place", headers=world.h_leo, json={"place": "habitica"})
    with SessionLocal() as db:
        db.query(HabiticaAccount).filter(HabiticaAccount.user_id == world.const).delete()
        db.commit()
    r = world.create(world.h_creator, assignee_id=world.const)
    assert r.status_code == 201, r.text
    assert r.json()["placed"]["provider"] == "hub_tasks"


def test_habitica_error_falls_back_to_hub_storage(client, world):
    world.http.post(f"{HABITICA}/api/v3/tasks/user").respond(500, json={"success": False})
    r = world.create(world.h_creator, assignee_id=world.const)
    assert r.status_code == 201, r.text
    assert r.json()["placed"] == {"provider": "hub_tasks", "fallback": True, "recipient": world.const}
    with SessionLocal() as db:
        assert db.query(TaskAssignment).filter_by(creator_id=world.creator, assignee_id=world.const).one().fallback
        assert db.query(HubTask).filter_by(uid=r.json()["uid"], assignee_id=world.const, created_by=world.creator).count() == 1


def test_nextcloud_write_error_falls_back_to_hub_storage(client, world):
    world.calendars["rt-mia"]._writable = False  # server answers 403
    r = world.create(world.h_creator, assignee_id=world.mia)
    assert r.status_code == 201, r.text
    assert r.json()["placed"]["provider"] == "hub_tasks" and r.json()["placed"]["fallback"] is True


def test_von_mir_survives_an_unreachable_recipient_provider(client, world):
    world.create(world.h_creator, assignee_id=world.mia)

    def boom(**kw):
        raise ConnectionError("down")
    with patch("caldav.DAVClient", side_effect=boom):
        data = _from_me(client, world.h_creator)
    assert [(t["title"], t["done"], t["stale"]) for t in data["items"]] == [("Müll", False, True)]


def test_task_removed_by_the_recipient_disappears_from_von_mir(client, world):
    world.create(world.h_creator, assignee_id=world.mia)
    world.calendars["rt-mia"]._todos_data.clear()  # she deletes it in her Nextcloud app
    assert _from_me(client, world.h_creator)["items"] == []


def test_unknown_or_guest_assignee_is_refused(client, world):
    assert world.create(world.h_creator, assignee_id=999999).status_code == 422


def test_retry_with_the_same_idempotency_key_creates_one_task(client, world):
    h = {**world.h_creator, "Idempotency-Key": str(uuid.uuid4())}
    a = world.create(h, assignee_id=world.mia)
    b = world.create(h, assignee_id=world.mia)
    assert a.status_code == b.status_code == 201
    assert len(_todos(world.calendars["rt-mia"])) == 1


# --- own and family tasks ---


def test_family_task_goes_to_the_family_list_of_nextcloud(client, world):
    r = world.create(world.h_creator, list="family")
    assert r.status_code == 201, r.text
    assert r.json()["placed"] == {"provider": "nextcloud", "fallback": False, "recipient": None}
    assert len(_todos(world.calendars["rt-creator-family"])) == 1
    assert _todos(world.calendars["rt-mia"]) == []


def test_family_task_honours_sources_per_area(client, world, monkeypatch):
    monkeypatch.setenv("TASKS_SOURCES", "hub_tasks,habitica")
    r = world.create(world.h_creator, list="family")
    assert r.status_code == 201, r.text
    assert r.json()["placed"]["provider"] == "hub_tasks"
    assert _todos(world.calendars["rt-creator-family"]) == []
    with SessionLocal() as db:
        assert db.query(HubTask).filter_by(uid=r.json()["uid"], family=True).count() == 1


def test_family_task_without_nextcloud_family_list_uses_the_hub(client, world):
    r = world.create(world.h_leo, list="family")  # Leo has no CalDAV account
    assert r.status_code == 201, r.text
    assert r.json()["placed"] == {"provider": "hub_tasks", "fallback": True, "recipient": None}


def test_household_rotation_goes_to_the_family_list(client, world):
    r = world.create(world.h_creator, list="family", recurrence="weekly", rotation=[world.creator, world.mia],
                     due="2099-01-02")
    assert r.status_code == 201, r.text
    assert r.json()["placed"]["provider"] == "nextcloud"
    assert "X-FAMILIENHUB-ROTATION" in _todos(world.calendars["rt-creator-family"])[0]


def test_own_task_goes_to_my_preferred_place(client, world):
    world.habitica_remote()
    r = world.create(world.h_leo)
    assert r.status_code == 201, r.text
    assert r.json()["placed"]["provider"] == "habitica" and world.remote_task["text"] == "Müll"
    r = world.create(world.h_mia)
    assert r.json()["placed"]["provider"] == "nextcloud"
    assert len(_todos(world.calendars["rt-mia"])) == 1
    r = world.create(world.h_creator, assignee_id=world.creator)  # assigning to myself is an own task
    assert r.json()["placed"]["provider"] == "nextcloud"


def test_explicit_provider_keeps_the_legacy_path(client, world):
    """Old clients name the provider themselves: no routing, no assignment record."""
    r = client.post("/api/tasks?provider=nextcloud", headers=world.h_mia, json={"title": "Alt"})
    assert r.status_code == 201, r.text
    assert "placed" not in r.json()
    assert len(_todos(world.calendars["rt-mia"])) == 1
    with SessionLocal() as db:
        assert db.query(TaskAssignment).filter_by(creator_id=world.mia).count() == 0
