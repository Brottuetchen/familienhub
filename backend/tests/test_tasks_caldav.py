"""Tests für Aufgaben über Nextcloud CalDAV (WP 2b)."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User


# --- Fake CalDAV Implementation ---

class FakeTodo:
    """Fake CalDAV Todo-Objekt."""

    def __init__(self, ical_str: str, url: str):
        self.data = ical_str
        self.url = url
        self._ical = None
        self._parent_calendar = None

    @property
    def icalendar_component(self):
        """Gibt die icalendar-Komponente zurück."""
        if self._ical is None:
            from icalendar import Calendar
            cal = Calendar.from_ical(self.data)
            for comp in cal.walk():
                if comp.name == "VTODO":
                    self._ical = comp
                    break
        return self._ical

    def save(self):
        """Speichert Änderungen zurück ins data."""
        from icalendar import Calendar

        # Baue neues iCal aus dem geänderten Component
        cal = Calendar()
        cal.add("prodid", "-//Test//NONSGML//EN")
        cal.add("version", "2.0")
        cal.add_component(self._ical)
        self.data = cal.to_ical().decode("utf-8")

        # Wenn ein Parent-Calendar vorhanden ist, aktualisiere dort auch
        if self._parent_calendar:
            self._parent_calendar._update_todo(self)

    def complete(self):
        """Markiert als erledigt."""
        comp = self.icalendar_component
        comp["status"] = "COMPLETED"
        comp["completed"] = datetime.utcnow()
        comp["percent-complete"] = 100
        self.save()

    def delete(self):
        """Löscht die Aufgabe."""
        pass


class FakeCalendar:
    """Fake CalDAV Calendar."""

    def __init__(self, name: str, supported_components: List[str], todos_data: Optional[List[str]] = None):
        self.name = name
        self.url = f"https://cloud.example.com/remote.php/dav/calendars/user/{name}"
        self._supported_components = supported_components
        self._todos_data = todos_data or []
        self._todos_objects: Dict[str, FakeTodo] = {}  # uid -> FakeTodo
        self._writable = True

    def get_supported_components(self) -> List[str]:
        """Gibt unterstützte Komponenten zurück."""
        return self._supported_components

    def todos(self, include_completed: bool = False, sort_keys=None, sort_key=None) -> List[FakeTodo]:
        """Gibt Todos zurück."""
        result = []
        for i, data in enumerate(self._todos_data):
            todo = FakeTodo(data, f"https://cloud.example.com/remote.php/dav/calendars/user/{self.name}/todo-{i}.ics")
            todo._parent_calendar = self

            # UID aus dem Todo extrahieren und cachen
            comp = todo.icalendar_component
            uid = str(comp.get("uid", ""))
            if uid:
                self._todos_objects[uid] = todo

            result.append(todo)
        return result

    def save_todo(self, ical: str) -> FakeTodo:
        """Speichert ein neues Todo."""
        if not self._writable:
            raise Exception("403: Forbidden")
        url = f"https://cloud.example.com/remote.php/dav/calendars/user/{self.name}/todo-{len(self._todos_data)}.ics"
        todo = FakeTodo(ical, url)
        todo._parent_calendar = self
        self._todos_data.append(ical)

        # UID cachen
        comp = todo.icalendar_component
        uid = str(comp.get("uid", ""))
        if uid:
            self._todos_objects[uid] = todo

        return todo

    def todo_by_uid(self, uid: str) -> Optional[FakeTodo]:
        """Findet Todo nach UID."""
        # Erst im Cache schauen
        if uid in self._todos_objects:
            return self._todos_objects[uid]

        # Sonst alle Todos durchsuchen
        for todo in self.todos(include_completed=True):
            comp = todo.icalendar_component
            if str(comp.get("uid")) == uid:
                return todo
        return None

    def _update_todo(self, todo: FakeTodo):
        """Aktualisiert ein Todo im internen Speicher (wird von FakeTodo.save() aufgerufen)."""
        comp = todo.icalendar_component
        uid = str(comp.get("uid", ""))

        # Finde den Index des alten Todos und ersetze es
        for i, data in enumerate(self._todos_data):
            from icalendar import Calendar
            cal = Calendar.from_ical(data)
            for c in cal.walk():
                if c.name == "VTODO" and str(c.get("uid")) == uid:
                    self._todos_data[i] = todo.data
                    return


class FakePrincipal:
    """Fake CalDAV Principal."""

    def __init__(self, calendars: List[FakeCalendar]):
        self._calendars = calendars

    def calendars(self) -> List[FakeCalendar]:
        """Gibt alle Kalender zurück."""
        return self._calendars


class FakeDAVClient:
    """Fake CalDAV Client."""

    def __init__(self, url: str, username: str, password: str, **kwargs):
        self.url = url
        self.username = username
        self.password = password
        self._principal = None

    def principal(self) -> FakePrincipal:
        """Gibt Principal zurück."""
        return self._principal


# --- Fixtures ---

@pytest.fixture()
def user_a():
    """Nutzer A (Anna)."""
    db = SessionLocal()
    try:
        # Alte Daten löschen
        from app.models.caldav import CalDAVAccount, TaskList

        user = db.query(User).filter(User.username == "anna").first()
        if not user:
            user = User(
                username="anna",
                email="anna@example.com",
                hashed_password=get_password_hash("test123"),
                full_name="Anna",
                role="admin",
                is_admin=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        user_id = user.id

        # CalDAV-Daten für diesen User löschen
        db.query(CalDAVAccount).filter(CalDAVAccount.user_id == user_id).delete()
        db.query(TaskList).filter(TaskList.user_id == user_id).delete()
        db.commit()

        # User-Objekt mit allen Attributen in ein Dict umwandeln
        return type('User', (), {
            'id': user_id,
            'username': user.username,
            'email': user.email,
            'full_name': user.full_name,
            'role': user.role,
        })()
    finally:
        db.close()


@pytest.fixture()
def user_b():
    """Nutzer B (Ben)."""
    db = SessionLocal()
    try:
        # Alte Daten löschen
        from app.models.caldav import CalDAVAccount, TaskList

        user = db.query(User).filter(User.username == "ben").first()
        if not user:
            user = User(
                username="ben",
                email="ben@example.com",
                hashed_password=get_password_hash("test123"),
                full_name="Ben",
                role="partner",
                is_admin=False,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        user_id = user.id

        # CalDAV-Daten für diesen User löschen
        db.query(CalDAVAccount).filter(CalDAVAccount.user_id == user_id).delete()
        db.query(TaskList).filter(TaskList.user_id == user_id).delete()
        db.commit()

        # User-Objekt mit allen Attributen in ein Dict umwandeln
        return type('User', (), {
            'id': user_id,
            'username': user.username,
            'email': user.email,
            'full_name': user.full_name,
            'role': user.role,
        })()
    finally:
        db.close()


@pytest.fixture()
def token_a(client, user_a):
    """Auth-Token für Nutzer A."""
    resp = client.post("/api/auth/login", json={"username": "anna", "password": "test123"})
    return resp.json()["access_token"]


@pytest.fixture()
def token_b(client, user_b):
    """Auth-Token für Nutzer B."""
    resp = client.post("/api/auth/login", json={"username": "ben", "password": "test123"})
    return resp.json()["access_token"]


@pytest.fixture()
def auth_a(token_a):
    """Auth-Header für Nutzer A."""
    return {"Authorization": f"Bearer {token_a}"}


@pytest.fixture()
def auth_b(token_b):
    """Auth-Header für Nutzer B."""
    return {"Authorization": f"Bearer {token_b}"}


def _make_vtodo(uid: str, summary: str, **props) -> str:
    """Erzeugt VTODO iCalendar-String."""
    from icalendar import Calendar, Todo

    cal = Calendar()
    cal.add("prodid", "-//Test//NONSGML//EN")
    cal.add("version", "2.0")

    todo = Todo()
    todo.add("uid", uid)
    todo.add("summary", summary)
    todo.add("dtstamp", datetime.utcnow())
    todo.add("created", datetime.utcnow())

    for key, value in props.items():
        if value is not None:
            todo.add(key, value)

    cal.add_component(todo)
    return cal.to_ical().decode("utf-8")


# --- Tests ---

def test_lists_only_vtodo_calendars(client, auth_a, user_a, monkeypatch):
    """Nur Kalender mit VTODO-Support werden als Task-Listen erkannt."""
    # Setup: CalDAV-Account für user_a
    from app.core.crypto import encrypt

    db = SessionLocal()
    try:
        from app.models.caldav import CalDAVAccount

        account = CalDAVAccount(
            user_id=user_a.id,
            url="https://cloud.example.com/remote.php/dav",
            username="anna",
            password_enc=encrypt("secret"),
        )
        db.add(account)
        db.commit()
    finally:
        db.close()

    # Mock CalDAV Client
    cal_tasks = FakeCalendar("tasks", ["VTODO"])
    cal_events = FakeCalendar("events", ["VEVENT"])
    cal_mixed = FakeCalendar("mixed", ["VEVENT", "VTODO"])

    fake_client = FakeDAVClient(
        url="https://cloud.example.com/remote.php/dav",
        username="anna",
        password="secret",
    )
    fake_client._principal = FakePrincipal([cal_tasks, cal_events, cal_mixed])

    with patch("caldav.DAVClient", return_value=fake_client):
        resp = client.get("/api/tasks/lists", headers=auth_a)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"

    # Nur "tasks" und "mixed" sollten zurückkommen
    list_names = [lst["display_name"] for lst in data["lists"]]
    assert "tasks" in list_names
    assert "mixed" in list_names
    assert "events" not in list_names


def test_view_mine(client, auth_a, user_a, monkeypatch):
    """Ansicht 'mine': Aufgaben in meiner personal-Liste, erstellt von mir oder ohne Ersteller."""
    # Setup
    db = SessionLocal()
    try:
        from app.core.crypto import encrypt
        from app.models.caldav import CalDAVAccount, TaskList

        account = CalDAVAccount(
            user_id=user_a.id,
            url="https://cloud.example.com/remote.php/dav",
            username="anna",
            password_enc=encrypt("secret"),
        )
        db.add(account)
        db.flush()

        task_list = TaskList(
            user_id=user_a.id,
            caldav_url="https://cloud.example.com/remote.php/dav/calendars/user/Anna",
            display_name="Anna",
            kind="personal",
            owner_user_id=user_a.id,
        )
        db.add(task_list)
        db.commit()
    finally:
        db.close()

    # Mock CalDAV
    uid1 = str(uuid4())
    uid2 = str(uuid4())

    todo1 = _make_vtodo(uid1, "Meine Aufgabe", **{"x-familienhub-created-by": str(user_a.id)})
    todo2 = _make_vtodo(uid2, "Aufgabe ohne Ersteller")

    cal = FakeCalendar("Anna", ["VTODO"], [todo1, todo2])
    fake_client = FakeDAVClient("https://cloud.example.com/remote.php/dav", "anna", "secret")
    fake_client._principal = FakePrincipal([cal])

    with patch("caldav.DAVClient", return_value=fake_client):
        resp = client.get("/api/tasks?view=mine", headers=auth_a)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert len(data["items"]) == 2


def test_view_for_me(client, auth_a, user_a, user_b, monkeypatch):
    """Ansicht 'for_me': Aufgaben in meiner Liste, erstellt von anderen."""
    db = SessionLocal()
    try:
        from app.core.crypto import encrypt
        from app.models.caldav import CalDAVAccount, TaskList

        account = CalDAVAccount(
            user_id=user_a.id,
            url="https://cloud.example.com/remote.php/dav",
            username="anna",
            password_enc=encrypt("secret"),
        )
        db.add(account)
        db.flush()

        task_list = TaskList(
            user_id=user_a.id,
            caldav_url="https://cloud.example.com/remote.php/dav/calendars/user/Anna",
            display_name="Anna",
            kind="personal",
            owner_user_id=user_a.id,
        )
        db.add(task_list)
        db.commit()
    finally:
        db.close()

    # Mock CalDAV
    uid1 = str(uuid4())
    uid2 = str(uuid4())

    # created_by = user_b (andere Person)
    todo1 = _make_vtodo(uid1, "Von Ben für Anna", **{"x-familienhub-created-by": str(user_b.id)})
    # created_by = user_a (ich selbst) -> soll NICHT in for_me sein
    todo2 = _make_vtodo(uid2, "Von mir selbst", **{"x-familienhub-created-by": str(user_a.id)})

    cal = FakeCalendar("Anna", ["VTODO"], [todo1, todo2])
    fake_client = FakeDAVClient("https://cloud.example.com/remote.php/dav", "anna", "secret")
    fake_client._principal = FakePrincipal([cal])

    with patch("caldav.DAVClient", return_value=fake_client):
        resp = client.get("/api/tasks?view=for_me", headers=auth_a)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert len(data["items"]) == 1
    assert data["items"][0]["title"] == "Von Ben für Anna"


def test_view_from_me(client, auth_a, user_a, user_b, monkeypatch):
    """Ansicht 'from_me': Aufgaben in fremden Listen, erstellt von mir."""
    db = SessionLocal()
    try:
        from app.core.crypto import encrypt
        from app.models.caldav import CalDAVAccount, TaskList

        # user_a hat Zugriff auf seine und Bens Listen
        account = CalDAVAccount(
            user_id=user_a.id,
            url="https://cloud.example.com/remote.php/dav",
            username="anna",
            password_enc=encrypt("secret"),
        )
        db.add(account)
        db.flush()

        # Liste von user_b
        task_list_b = TaskList(
            user_id=user_a.id,  # user_a hat Zugriff
            caldav_url="https://cloud.example.com/remote.php/dav/calendars/user/Ben",
            display_name="Ben",
            kind="personal",
            owner_user_id=user_b.id,  # gehört aber user_b
        )
        db.add(task_list_b)
        db.commit()
    finally:
        db.close()

    # Mock CalDAV
    uid1 = str(uuid4())

    # In Bens Liste, erstellt von Anna
    todo1 = _make_vtodo(uid1, "Von Anna für Ben", **{"x-familienhub-created-by": str(user_a.id)})

    cal = FakeCalendar("Ben", ["VTODO"], [todo1])
    fake_client = FakeDAVClient("https://cloud.example.com/remote.php/dav", "anna", "secret")
    fake_client._principal = FakePrincipal([cal])

    with patch("caldav.DAVClient", return_value=fake_client):
        resp = client.get("/api/tasks?view=from_me", headers=auth_a)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert len(data["items"]) == 1
    assert data["items"][0]["title"] == "Von Anna für Ben"


def test_view_family(client, auth_a, user_a, monkeypatch):
    """Ansicht 'family': Aufgaben in der Familie-Liste."""
    db = SessionLocal()
    try:
        from app.core.crypto import encrypt
        from app.models.caldav import CalDAVAccount, TaskList

        account = CalDAVAccount(
            user_id=user_a.id,
            url="https://cloud.example.com/remote.php/dav",
            username="anna",
            password_enc=encrypt("secret"),
        )
        db.add(account)
        db.flush()

        task_list = TaskList(
            user_id=user_a.id,
            caldav_url="https://cloud.example.com/remote.php/dav/calendars/user/Familie",
            display_name="Familie",
            kind="family",
            owner_user_id=None,  # family hat keinen owner
        )
        db.add(task_list)
        db.commit()
    finally:
        db.close()

    # Mock CalDAV
    uid1 = str(uuid4())
    todo1 = _make_vtodo(uid1, "Familienaufgabe")

    cal = FakeCalendar("Familie", ["VTODO"], [todo1])
    fake_client = FakeDAVClient("https://cloud.example.com/remote.php/dav", "anna", "secret")
    fake_client._principal = FakePrincipal([cal])

    with patch("caldav.DAVClient", return_value=fake_client):
        resp = client.get("/api/tasks?view=family", headers=auth_a)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert len(data["items"]) == 1
    assert data["items"][0]["title"] == "Familienaufgabe"


def test_view_all_excludes_hidden(client, auth_a, user_a, monkeypatch):
    """Ansicht 'all' schließt hidden-Listen aus."""
    db = SessionLocal()
    try:
        from app.core.crypto import encrypt
        from app.models.caldav import CalDAVAccount, TaskList

        account = CalDAVAccount(
            user_id=user_a.id,
            url="https://cloud.example.com/remote.php/dav",
            username="anna",
            password_enc=encrypt("secret"),
        )
        db.add(account)
        db.flush()

        # Personal-Liste
        task_list_personal = TaskList(
            user_id=user_a.id,
            caldav_url="https://cloud.example.com/remote.php/dav/calendars/user/Anna",
            display_name="Anna",
            kind="personal",
            owner_user_id=user_a.id,
        )
        db.add(task_list_personal)

        # Hidden-Liste (Habitica)
        task_list_hidden = TaskList(
            user_id=user_a.id,
            caldav_url="https://cloud.example.com/remote.php/dav/calendars/user/Habitica",
            display_name="Habitica",
            kind="hidden",
            owner_user_id=user_a.id,
        )
        db.add(task_list_hidden)
        db.commit()
    finally:
        db.close()

    # Mock CalDAV
    uid1 = str(uuid4())
    uid2 = str(uuid4())

    todo1 = _make_vtodo(uid1, "Sichtbare Aufgabe")
    todo2 = _make_vtodo(uid2, "Habitica-Aufgabe")

    cal_personal = FakeCalendar("Anna", ["VTODO"], [todo1])
    cal_hidden = FakeCalendar("Habitica", ["VTODO"], [todo2])

    fake_client = FakeDAVClient("https://cloud.example.com/remote.php/dav", "anna", "secret")
    fake_client._principal = FakePrincipal([cal_personal, cal_hidden])

    with patch("caldav.DAVClient", return_value=fake_client):
        resp = client.get("/api/tasks?view=all", headers=auth_a)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert len(data["items"]) == 1
    assert data["items"][0]["title"] == "Sichtbare Aufgabe"


def test_create_for_other_lands_in_their_list_with_x_props(client, auth_a, user_a, user_b, monkeypatch):
    """Aufgabe für andere Person landet in deren Liste mit X-FAMILIENHUB-* Properties."""
    db = SessionLocal()
    try:
        from app.core.crypto import encrypt
        from app.models.caldav import CalDAVAccount, TaskList

        account = CalDAVAccount(
            user_id=user_a.id,
            url="https://cloud.example.com/remote.php/dav",
            username="anna",
            password_enc=encrypt("secret"),
        )
        db.add(account)
        db.flush()

        # Liste von user_b (mit Schreibrecht für user_a)
        task_list_b = TaskList(
            user_id=user_a.id,
            caldav_url="https://cloud.example.com/remote.php/dav/calendars/user/Ben",
            display_name="Ben",
            kind="personal",
            owner_user_id=user_b.id,
        )
        db.add(task_list_b)
        db.commit()
    finally:
        db.close()

    # Mock CalDAV
    cal_b = FakeCalendar("Ben", ["VTODO"], [])
    fake_client = FakeDAVClient("https://cloud.example.com/remote.php/dav", "anna", "secret")
    fake_client._principal = FakePrincipal([cal_b])

    with patch("caldav.DAVClient", return_value=fake_client):
        resp = client.post(
            "/api/tasks",
            headers=auth_a,
            json={
                "title": "Aufgabe für Ben",
                "assignee_id": user_b.id,
            },
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Aufgabe für Ben"
    assert data["created_by"] == user_a.id
    assert data["assignee"] == user_b.id
    assert data["list"]["name"] == "Ben"


def test_create_for_other_without_write_access_returns_409(client, auth_a, user_a, user_b, monkeypatch):
    """Fehlende Schreibrechte auf fremder Liste → HTTP 409."""
    db = SessionLocal()
    try:
        from app.core.crypto import encrypt
        from app.models.caldav import CalDAVAccount, TaskList

        account = CalDAVAccount(
            user_id=user_a.id,
            url="https://cloud.example.com/remote.php/dav",
            username="anna",
            password_enc=encrypt("secret"),
        )
        db.add(account)
        db.flush()

        task_list_b = TaskList(
            user_id=user_a.id,
            caldav_url="https://cloud.example.com/remote.php/dav/calendars/user/Ben",
            display_name="Ben",
            kind="personal",
            owner_user_id=user_b.id,
        )
        db.add(task_list_b)
        db.commit()
    finally:
        db.close()

    # Mock CalDAV: Kalender ohne Schreibrecht
    cal_b = FakeCalendar("Ben", ["VTODO"], [])
    cal_b._writable = False

    fake_client = FakeDAVClient("https://cloud.example.com/remote.php/dav", "anna", "secret")
    fake_client._principal = FakePrincipal([cal_b])

    with patch("caldav.DAVClient", return_value=fake_client):
        resp = client.post(
            "/api/tasks",
            headers=auth_a,
            json={
                "title": "Sollte fehlschlagen",
                "assignee_id": user_b.id,
            },
        )

    assert resp.status_code == 409
    data = resp.json()
    assert data["detail"]["error"] == "no_write_access"
    assert data["detail"]["list"] == "Ben"


def test_update_preserves_unknown_properties(client, auth_a, user_a, monkeypatch):
    """Update erhält unbekannte Properties wie X-APPLE-SORT-ORDER, CATEGORIES."""
    db = SessionLocal()
    try:
        from app.core.crypto import encrypt
        from app.models.caldav import CalDAVAccount, TaskList

        account = CalDAVAccount(
            user_id=user_a.id,
            url="https://cloud.example.com/remote.php/dav",
            username="anna",
            password_enc=encrypt("secret"),
        )
        db.add(account)
        db.flush()

        task_list = TaskList(
            user_id=user_a.id,
            caldav_url="https://cloud.example.com/remote.php/dav/calendars/user/Anna",
            display_name="Anna",
            kind="personal",
            owner_user_id=user_a.id,
        )
        db.add(task_list)
        db.commit()
    finally:
        db.close()

    # Mock CalDAV: VTODO mit Apple-Properties
    uid = str(uuid4())
    todo_with_apple = _make_vtodo(
        uid,
        "Aufgabe mit Apple-Properties",
        **{
            "x-apple-sort-order": "123",
            "categories": ["Work", "Important"],
        }
    )

    cal = FakeCalendar("Anna", ["VTODO"], [todo_with_apple])
    fake_client = FakeDAVClient("https://cloud.example.com/remote.php/dav", "anna", "secret")
    fake_client._principal = FakePrincipal([cal])

    with patch("caldav.DAVClient", return_value=fake_client):
        # Update nur den Titel
        resp = client.patch(
            f"/api/tasks/{uid}",
            headers=auth_a,
            json={"title": "Neuer Titel"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Neuer Titel"

    # Prüfe, dass die Apple-Properties erhalten blieben (im echten Test würde man das VTODO prüfen)
    # Hier simulieren wir das durch Auslesen des Fake-Objekts
    todo_obj = cal.todo_by_uid(uid)
    assert todo_obj is not None
    comp = todo_obj.icalendar_component
    assert comp.get("x-apple-sort-order") == "123"
    assert "Work" in comp.get("categories", [])


def test_complete_sets_status_completed_and_percent(client, auth_a, user_a, monkeypatch):
    """Complete setzt STATUS:COMPLETED, COMPLETED und PERCENT-COMPLETE:100."""
    db = SessionLocal()
    try:
        from app.core.crypto import encrypt
        from app.models.caldav import CalDAVAccount, TaskList

        account = CalDAVAccount(
            user_id=user_a.id,
            url="https://cloud.example.com/remote.php/dav",
            username="anna",
            password_enc=encrypt("secret"),
        )
        db.add(account)
        db.flush()

        task_list = TaskList(
            user_id=user_a.id,
            caldav_url="https://cloud.example.com/remote.php/dav/calendars/user/Anna",
            display_name="Anna",
            kind="personal",
            owner_user_id=user_a.id,
        )
        db.add(task_list)
        db.commit()
    finally:
        db.close()

    # Mock CalDAV
    uid = str(uuid4())
    todo_data = _make_vtodo(uid, "Zu erledigende Aufgabe")

    cal = FakeCalendar("Anna", ["VTODO"], [todo_data])
    fake_client = FakeDAVClient("https://cloud.example.com/remote.php/dav", "anna", "secret")
    fake_client._principal = FakePrincipal([cal])

    with patch("caldav.DAVClient", return_value=fake_client):
        resp = client.post(f"/api/tasks/{uid}/complete", headers=auth_a)

    assert resp.status_code == 200
    data = resp.json()
    assert data["done"] is True

    # Prüfe das Todo-Objekt
    todo_obj = cal.todo_by_uid(uid)
    comp = todo_obj.icalendar_component
    assert str(comp.get("status")).upper() == "COMPLETED"
    assert comp.get("completed") is not None
    assert comp.get("percent-complete") == 100


def test_assignment_triggers_notify_once(client, auth_a, user_a, user_b, monkeypatch):
    """Zuweisung an anderen Nutzer triggert notify genau einmal."""
    db = SessionLocal()
    try:
        from app.core.crypto import encrypt
        from app.models.caldav import CalDAVAccount, TaskList

        account = CalDAVAccount(
            user_id=user_a.id,
            url="https://cloud.example.com/remote.php/dav",
            username="anna",
            password_enc=encrypt("secret"),
        )
        db.add(account)
        db.flush()

        task_list_b = TaskList(
            user_id=user_a.id,
            caldav_url="https://cloud.example.com/remote.php/dav/calendars/user/Ben",
            display_name="Ben",
            kind="personal",
            owner_user_id=user_b.id,
        )
        db.add(task_list_b)
        db.commit()
    finally:
        db.close()

    # Mock CalDAV
    cal_b = FakeCalendar("Ben", ["VTODO"], [])
    fake_client = FakeDAVClient("https://cloud.example.com/remote.php/dav", "anna", "secret")
    fake_client._principal = FakePrincipal([cal_b])

    # Mock notify
    notify_calls = []

    async def mock_notify(user_id, title, body, data, category):
        notify_calls.append({"user_id": user_id, "category": category, "data": data})

    with patch("caldav.DAVClient", return_value=fake_client):
        with patch("app.services.notify.notify", side_effect=mock_notify):
            resp = client.post(
                "/api/tasks",
                headers=auth_a,
                json={
                    "title": "Neue Zuweisung",
                    "assignee_id": user_b.id,
                },
            )

    assert resp.status_code == 201
    assert len(notify_calls) == 1
    assert notify_calls[0]["user_id"] == user_b.id
    assert notify_calls[0]["category"] == "task_assigned"
    # Die App öffnet beim Tippen „Für mich“
    assert notify_calls[0]["data"]["route"] == "/tasks?view=for_me"


def test_self_assignment_does_not_notify(client, auth_a, user_a, monkeypatch):
    """Selbstzuweisung triggert keine Benachrichtigung."""
    db = SessionLocal()
    try:
        from app.core.crypto import encrypt
        from app.models.caldav import CalDAVAccount, TaskList

        account = CalDAVAccount(
            user_id=user_a.id,
            url="https://cloud.example.com/remote.php/dav",
            username="anna",
            password_enc=encrypt("secret"),
        )
        db.add(account)
        db.flush()

        task_list = TaskList(
            user_id=user_a.id,
            caldav_url="https://cloud.example.com/remote.php/dav/calendars/user/Anna",
            display_name="Anna",
            kind="personal",
            owner_user_id=user_a.id,
        )
        db.add(task_list)
        db.commit()
    finally:
        db.close()

    # Mock CalDAV
    cal = FakeCalendar("Anna", ["VTODO"], [])
    fake_client = FakeDAVClient("https://cloud.example.com/remote.php/dav", "anna", "secret")
    fake_client._principal = FakePrincipal([cal])

    # Mock notify
    notify_calls = []

    async def mock_notify(user_id, title, body, data, category):
        notify_calls.append({"user_id": user_id})

    with patch("caldav.DAVClient", return_value=fake_client):
        with patch("app.services.notify.notify", side_effect=mock_notify):
            resp = client.post(
                "/api/tasks",
                headers=auth_a,
                json={
                    "title": "Für mich selbst",
                    "assignee_id": user_a.id,
                },
            )

    assert resp.status_code == 201
    assert len(notify_calls) == 0


def test_caldav_password_encrypted_and_not_returned(client, auth_a, user_a):
    """CalDAV-Passwort wird verschlüsselt gespeichert und nicht zurückgegeben."""
    # Passwort setzen
    resp = client.put(
        "/api/tasks/me/caldav",
        headers=auth_a,
        json={
            "url": "https://cloud.example.com/remote.php/dav",
            "username": "anna",
            "password": "secret123",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["url"] == "https://cloud.example.com/remote.php/dav"
    assert data["username"] == "anna"
    assert data["has_password"] is True
    assert "password" not in data

    # Passwort aus DB prüfen
    from app.core.crypto import decrypt
    from app.models.caldav import CalDAVAccount

    db = SessionLocal()
    try:
        account = db.query(CalDAVAccount).filter(CalDAVAccount.user_id == user_a.id).first()
        assert account is not None
        assert account.password_enc != "secret123"
        assert decrypt(account.password_enc) == "secret123"
    finally:
        db.close()

    # Erneutes GET gibt auch kein Passwort zurück
    resp = client.get("/api/tasks/me/caldav", headers=auth_a)
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_password"] is True
    assert "password" not in data


def test_unreachable_server_returns_status_unavailable(client, auth_a, user_a, monkeypatch):
    """Nicht erreichbarer CalDAV-Server → status: unavailable."""
    db = SessionLocal()
    try:
        from app.core.crypto import encrypt
        from app.models.caldav import CalDAVAccount, TaskList

        account = CalDAVAccount(
            user_id=user_a.id,
            url="https://unreachable.example.com/dav",
            username="test",
            password_enc=encrypt("test"),
        )
        db.add(account)
        db.flush()

        # TaskList hinzufügen, damit der Connector versucht, darauf zuzugreifen
        task_list = TaskList(
            user_id=user_a.id,
            caldav_url="https://unreachable.example.com/dav/calendars/user/test",
            display_name="Test",
            kind="personal",
            owner_user_id=user_a.id,
        )
        db.add(task_list)
        db.commit()
    finally:
        db.close()

    # Mock _get_client, um Connection-Fehler zu simulieren
    from app.connectors.nextcloud_tasks_connector import NextcloudTasksConnector

    def mock_get_client(self):
        raise Exception("Connection refused")

    with patch.object(NextcloudTasksConnector, '_get_client', mock_get_client):
        resp = client.get("/api/tasks?view=all", headers=auth_a)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unavailable"
    assert data["error"] is not None
    assert len(data["items"]) == 0


def test_habitica_failure_does_not_block_completion(client, auth_a, user_a, monkeypatch):
    """Habitica-Fehler beim Erledigen blockiert die Aufgaben-Completion nicht."""
    db = SessionLocal()
    try:
        from app.core.crypto import encrypt
        from app.models.caldav import CalDAVAccount, TaskList

        account = CalDAVAccount(
            user_id=user_a.id,
            url="https://cloud.example.com/remote.php/dav",
            username="anna",
            password_enc=encrypt("secret"),
        )
        db.add(account)
        db.flush()

        task_list = TaskList(
            user_id=user_a.id,
            caldav_url="https://cloud.example.com/remote.php/dav/calendars/user/Anna",
            display_name="Anna",
            kind="personal",
            owner_user_id=user_a.id,
        )
        db.add(task_list)
        db.commit()
    finally:
        db.close()

    # Mock CalDAV
    uid = str(uuid4())
    todo_data = _make_vtodo(uid, "Aufgabe")

    cal = FakeCalendar("Anna", ["VTODO"], [todo_data])
    fake_client = FakeDAVClient("https://cloud.example.com/remote.php/dav", "anna", "secret")
    fake_client._principal = FakePrincipal([cal])

    # Mock Habitica-Service: Exception
    async def mock_habitica_score(*args, **kwargs):
        raise Exception("Habitica API down")

    with patch("caldav.DAVClient", return_value=fake_client):
        with patch("app.services.habitica.score_up", side_effect=mock_habitica_score):
            resp = client.post(f"/api/tasks/{uid}/complete", headers=auth_a)

    # Trotzdem erfolgreich
    assert resp.status_code == 200
    data = resp.json()
    assert data["done"] is True


def test_shared_foreign_personal_list_not_in_mine_or_for_me(client, auth_a, user_a, user_b, monkeypatch):
    """Geteilte private Liste von B (für Zuweisungen) erscheint bei A nicht unter „Meine“/„Für mich“.

    Im Betrieb (14.10.) sah Ben sonst Annas Habitica-Aufgaben als ihre eigenen.
    """
    db = SessionLocal()
    try:
        from app.core.crypto import encrypt
        from app.models.caldav import CalDAVAccount, TaskList

        db.add(CalDAVAccount(user_id=user_a.id, url="https://cloud.example.com/remote.php/dav",
                             username="a", password_enc=encrypt("secret")))
        db.add(TaskList(user_id=user_a.id, caldav_url="https://cloud.example.com/remote.php/dav/calendars/user/Eigene",
                        display_name="Eigene", kind="personal", owner_user_id=user_a.id))
        db.add(TaskList(user_id=user_a.id, caldav_url="https://cloud.example.com/remote.php/dav/calendars/user/VonB",
                        display_name="VonB", kind="personal", owner_user_id=user_b.id))
        db.commit()
    finally:
        db.close()

    own = FakeCalendar("Eigene", ["VTODO"], [
        _make_vtodo(str(uuid4()), "Meins"),
        _make_vtodo(str(uuid4()), "Von B für mich", **{"x-familienhub-created-by": str(user_b.id)}),
    ])
    foreign = FakeCalendar("VonB", ["VTODO"], [
        _make_vtodo(str(uuid4()), "Bs eigene Aufgabe"),
        _make_vtodo(str(uuid4()), "Von mir für B", **{"x-familienhub-created-by": str(user_a.id)}),
    ])
    fake_client = FakeDAVClient("https://cloud.example.com/remote.php/dav", "a", "secret")
    fake_client._principal = FakePrincipal([own, foreign])

    with patch("caldav.DAVClient", return_value=fake_client):
        mine = client.get("/api/tasks?view=mine", headers=auth_a).json()
        for_me = client.get("/api/tasks?view=for_me", headers=auth_a).json()
        from_me = client.get("/api/tasks?view=from_me", headers=auth_a).json()

    assert [t["title"] for t in mine["items"]] == ["Meins"]
    assert [t["title"] for t in for_me["items"]] == ["Von B für mich"]
    assert [t["title"] for t in from_me["items"]] == ["Von mir für B"]


def test_legacy_habitica_mirrors_are_hidden(client, auth_a, user_a, monkeypatch):
    """Spiegel des alten Habitica→Nextcloud-Skripts (UID habitica-…) erscheinen nicht mehr.

    Habitica-Aufgaben kommen nativ über das Habitica-Plugin; die Spiegel waren schreibgeschützte Doppelte.
    """
    db = SessionLocal()
    try:
        from app.core.crypto import encrypt
        from app.models.caldav import CalDAVAccount, TaskList

        if not db.query(CalDAVAccount).filter(CalDAVAccount.user_id == user_a.id).first():
            db.add(CalDAVAccount(user_id=user_a.id, url="https://cloud.example.com/remote.php/dav",
                                 username="anna", password_enc=encrypt("secret")))
        db.query(TaskList).filter(TaskList.user_id == user_a.id).delete()
        db.add(TaskList(user_id=user_a.id, caldav_url="https://cloud.example.com/remote.php/dav/calendars/user/Habitica",
                        display_name="Habitica", kind="family", owner_user_id=None))
        db.commit()
    finally:
        db.close()

    cal = FakeCalendar("Habitica", ["VTODO"], [
        _make_vtodo("habitica-4f1c2b", "2 Liter Wasser"),
        _make_vtodo(str(uuid4()), "Echte Aufgabe"),
    ])
    fake_client = FakeDAVClient("https://cloud.example.com/remote.php/dav", "anna", "secret")
    fake_client._principal = FakePrincipal([cal])
    with patch("caldav.DAVClient", return_value=fake_client):
        resp = client.get("/api/tasks?view=family", headers=auth_a)

    assert resp.status_code == 200
    assert [t["title"] for t in resp.json()["items"]] == ["Echte Aufgabe"]
