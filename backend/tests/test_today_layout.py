"""Customisable Today layout: per-person, family default, reset, validation."""

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User

ME, ADMIN = "/api/me/today-layout", "/api/admin/today-layout"
IDS = ["tasks", "shopping", "events", "meals", "reminders", "house", "birthdays", "timetable"]


def _partner(client, name):
    with SessionLocal() as db:
        if not db.query(User).filter(User.username == name).first():
            db.add(User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"), role="partner"))
            db.commit()
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _cards(order, hidden=(), half=()):
    return [{"id": i, "visible": i not in hidden, "size": "half" if i in half else "full"} for i in order]


def test_builtin_default_matches_original_arrangement(client, auth):
    client.delete(ADMIN, headers=auth)
    body = client.get(ME, headers=_partner(client, "tl_a")).json()
    assert body["source"] == "builtin"
    assert [c["id"] for c in body["cards"]] == IDS
    assert {c["id"] for c in body["cards"] if c["size"] == "half"} == {"shopping", "events"}
    assert all(c["visible"] for c in body["cards"])


def test_layout_is_per_person_and_resettable(client, auth):
    client.delete(ADMIN, headers=auth)
    a, b = _partner(client, "tl_b1"), _partner(client, "tl_b2")
    order = ["meals", "tasks", "house", "events", "shopping", "reminders", "birthdays", "timetable"]
    r = client.put(ME, headers=a, json={"cards": _cards(order, hidden=("house",))})
    assert r.status_code == 200 and r.json()["source"] == "user"
    got = client.get(ME, headers=a).json()["cards"]
    assert [c["id"] for c in got] == order and not got[2]["visible"]
    assert client.get(ME, headers=b).json()["source"] == "builtin"
    reset = client.delete(ME, headers=a).json()
    assert reset["source"] == "builtin" and [c["id"] for c in reset["cards"]] == IDS


def test_missing_cards_are_appended(client, auth):
    h = _partner(client, "tl_c")
    r = client.put(ME, headers=h, json={"cards": _cards(["house", "meals"])})
    assert [c["id"] for c in r.json()["cards"]] == ["house", "meals", "tasks", "shopping", "events", "reminders", "birthdays", "timetable"]


def test_admin_default_is_fallback_and_user_wins(client, auth):
    h = _partner(client, "tl_d")
    r = client.put(ADMIN, headers=auth, json={"cards": _cards(["events", "tasks", "meals"], hidden=("meals",))})
    assert r.status_code == 200
    try:
        eff = client.get(ME, headers=h).json()
        assert eff["source"] == "family" and eff["cards"][0]["id"] == "events"
        assert not next(c for c in eff["cards"] if c["id"] == "meals")["visible"]
        client.put(ME, headers=h, json={"cards": _cards(IDS)})
        assert client.get(ME, headers=h).json()["source"] == "user"
        assert client.delete(ME, headers=h).json()["source"] == "family"
        assert client.get(ADMIN, headers=auth).json()["source"] == "family"
    finally:
        client.delete(ADMIN, headers=auth)
    assert client.get(ADMIN, headers=auth).json()["source"] == "builtin"


def test_non_admin_cannot_touch_default(client, auth):
    h = _partner(client, "tl_e")
    for call in (client.get(ADMIN, headers=h), client.put(ADMIN, headers=h, json={"cards": []}),
                 client.delete(ADMIN, headers=h)):
        assert call.status_code == 403
    assert client.get(ME).status_code in (401, 403)


def test_validation(client):
    h = _partner(client, "tl_f")
    bad = [
        {"cards": [{"id": "nope", "visible": True, "size": "full"}]},
        {"cards": [{"id": "tasks", "visible": True, "size": "huge"}]},
        {"cards": [{"id": "tasks"}, {"id": "tasks"}]},
        {"cards": [{"id": "tasks"}] * 50},
        {"cards": "tasks"},
        {},
    ]
    for body in bad:
        assert client.put(ME, headers=h, json=body).status_code == 422, body
