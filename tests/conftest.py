import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest"
os.environ["OPENAI_API_KEY"] = "test-key"

import database  # noqa: E402

database.engine = create_engine(
    database.DATABASE_URL,
    connect_args={"check_same_thread": False},
)
database.SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=database.engine,
)

import models  # noqa: E402, F401
from database import Base, get_db, engine, SessionLocal  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture
def client():
    Base.metadata.create_all(bind=engine)
    connection = engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)
    session.begin_nested()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client

    session.close()
    transaction.rollback()
    connection.close()
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def mock_openai():
    with patch("main.client") as mock_client:
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="food"))]
        )
        yield mock_client


@pytest.fixture(autouse=True)
def mock_redis():
    store = {}

    def get_cached(key):
        return store.get(key)

    def set_cached(key, value, ttl=60):
        store[key] = value

    def delete_cached(key):
        store.pop(key, None)

    with (
        patch("main.get_cached", side_effect=get_cached),
        patch("main.set_cached", side_effect=set_cached),
        patch("main.delete_cached", side_effect=delete_cached),
    ):
        yield store


@pytest.fixture
def auth_headers(client):
    client.post("/register", json={"username": "testuser", "password": "secret"})
    response = client.post(
        "/token",
        data={"username": "testuser", "password": "secret"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
