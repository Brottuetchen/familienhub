"""Offline-Warteschlange (#32): Wiederholte Anlage mit gleichem Idempotency-Key legt nur einmal an."""

import pytest

from app.routers import shopping
from app.services import idempotency


class FakeHA:
    def __init__(self, fail_first=False):
        self.added = []
        self.fail_first = fail_first

    async def add_todo_item(self, entity, item):
        if self.fail_first and not self.added and not getattr(self, "_failed", False):
            self._failed = True
            return False
        self.added.append(item)
        return True


@pytest.fixture
def ha(monkeypatch):
    idempotency.clear()
    fake = FakeHA()
    monkeypatch.setattr(shopping, "_ha", lambda: fake)
    yield fake
    idempotency.clear()


def test_same_key_adds_once(client, auth, ha):
    h = {**auth, "Idempotency-Key": "offline-0001-milch"}
    for _ in range(3):
        assert client.post("/api/shopping", headers=h, json={"item": "Milch"}).json() == {"status": "ok"}
    assert ha.added == ["Milch"]


def test_without_key_unchanged(client, auth, ha):
    for _ in range(2):
        client.post("/api/shopping", headers=auth, json={"item": "Brot"})
    assert ha.added == ["Brot", "Brot"]


def test_keys_are_per_user_and_invalid_rejected(client, auth, ha):
    assert client.post("/api/shopping", headers={**auth, "Idempotency-Key": "kurz"}, json={"item": "X"}).status_code == 422
    assert client.post("/api/shopping", headers={**auth, "Idempotency-Key": "../../etc"}, json={"item": "X"}).status_code == 422
    assert ha.added == []


def test_failure_is_not_remembered(client, auth, monkeypatch):
    idempotency.clear()
    fake = FakeHA(fail_first=True)
    monkeypatch.setattr(shopping, "_ha", lambda: fake)
    h = {**auth, "Idempotency-Key": "offline-0002-eier"}
    assert client.post("/api/shopping", headers=h, json={"item": "Eier"}).status_code == 502
    assert client.post("/api/shopping", headers=h, json={"item": "Eier"}).status_code == 200
    assert fake.added == ["Eier"]
