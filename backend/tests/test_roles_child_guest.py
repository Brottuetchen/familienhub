"""Rollen Kind und Gast (Entscheidung 18.10.): lesen ja, Schreiben nur, was zur Rolle passt.

Erwartet wird nur „403 oder nicht 403“: erlaubte Aufrufe dürfen aus anderen Gründen scheitern (Dienst nicht
eingerichtet, Eintrag fehlt), sie dürfen nur nicht an der Rolle scheitern.
"""

import pytest

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User


def _login(client, role):
    name = f"rolle_{role}"
    with SessionLocal() as db:
        if not db.query(User).filter(User.username == name).first():
            db.add(User(username=name, email=f"{name}@test.de", hashed_password=get_password_hash("pw-12345"), role=role))
            db.commit()
    tok = client.post("/api/auth/login", json={"username": name, "password": "pw-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


# (Methode, Pfad, Body, Mindestrolle)
CASES = [
    ("post", "/api/shopping", {"item": "Milch"}, "guest"),
    ("patch", "/api/shopping/x1", {"done": True}, "guest"),
    ("delete", "/api/shopping/x1", None, "child"),
    ("post", "/api/reminders", {"title": "Eigene"}, "guest"),
    ("post", "/api/reminders", {"title": "Alle", "for_family": True}, "partner"),
    ("post", "/api/tasks/t1/complete", None, "child"),
    ("post", "/api/books/requests", {"work_id": "ol:1", "book_type": "ebook", "title": "Momo"}, "child"),
    ("post", "/api/tasks", {"title": "Neu"}, "partner"),
    ("patch", "/api/tasks/t1", {"title": "Anders"}, "partner"),
    ("delete", "/api/tasks/t1", None, "partner"),
    ("post", "/api/meals/plan", {"date": "2026-10-20", "custom_title": "Suppe", "meal_type": "dinner"}, "partner"),
    ("delete", "/api/meals/plan/1", None, "partner"),
    ("post", "/api/recipes", {"title": "Kuchen"}, "partner"),
    ("delete", "/api/recipes/1", None, "partner"),
    ("post", "/api/calendar/events", {"title": "Termin", "start": "2026-10-20T10:00:00", "end": "2026-10-20T11:00:00"}, "partner"),
]
LEVEL = {"guest": 0, "child": 1, "partner": 2}


@pytest.mark.parametrize("role", ["guest", "child", "partner"])
@pytest.mark.parametrize("method,path,body,minimum", CASES)
def test_role_matrix(client, role, method, path, body, minimum):
    h = _login(client, role)
    kwargs = {"headers": h}
    if body is not None:
        kwargs["json"] = body
    r = getattr(client, method)(path, **kwargs)
    if LEVEL[role] >= LEVEL[minimum]:
        assert r.status_code != 403, (role, path, r.text)
    else:
        assert r.status_code == 403, (role, path, r.status_code, r.text)


@pytest.mark.parametrize("role", ["guest", "child"])
def test_reading_stays_allowed(client, role):
    h = _login(client, role)
    for path in ("/api/today", "/api/shopping", "/api/reminders", "/api/meals?week=2026-W43"):
        assert client.get(path, headers=h).status_code != 403, path


@pytest.mark.parametrize("role,allowed", [("guest", False), ("child", True), ("partner", True)])
def test_family_reminder_complete_from_child(client, role, allowed):
    """Abhaken einer Familien-Erinnerung ab Kind (wie Aufgaben und der Knopf in der Mitteilung), ändern nicht."""
    family = client.post("/api/reminders", json={"title": "Müll raus", "for_family": True},
                         headers=_login(client, "partner")).json()
    h = _login(client, role)
    done = client.patch(f"/api/reminders/{family['id']}", json={"completed": True}, headers=h)
    assert (done.status_code == 200) is allowed, (role, done.status_code, done.text)
    if role != "partner":
        changed = client.patch(f"/api/reminders/{family['id']}", json={"title": "Anders"}, headers=h)
        assert changed.status_code == 403, (role, changed.status_code)
