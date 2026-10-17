"""Pytest-Fixtures für Hermes.

WICHTIG: Umgebungsvariablen müssen VOR dem Import der App gesetzt werden, da
die Settings (lru_cache) beim ersten Import eingefroren werden.
"""

import os
import tempfile

_DB_PATH = os.path.join(tempfile.gettempdir(), "hermes_pytest.db")
if os.path.exists(_DB_PATH):
    os.remove(_DB_PATH)

os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ["SECRET_KEY"] = "pytest-secret"
os.environ["WEATHER_ENABLED"] = "false"
os.environ["AI_PROVIDER"] = "none"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import SessionLocal, init_db  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _init_db():
    init_db()
    yield


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def admin_token(client):
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "admin").first():
            db.add(
                User(
                    username="admin",
                    email="admin@test.de",
                    hashed_password=get_password_hash("secret123"),
                    full_name="Admin",
                    role="admin",
                    is_admin=True,
                )
            )
            db.commit()
    finally:
        db.close()
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    return resp.json()["access_token"]


@pytest.fixture()
def auth(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture()
def session():
    """Gibt eine DB-Session zurück."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
