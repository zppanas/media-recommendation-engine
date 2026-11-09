import os
import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from app.database import create_database_engine, init_db, get_session
from app.main import app


@pytest.fixture
def isolated_client(tmp_path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'auth.db'}")
    init_db(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    def override():
        with sessions() as session:
            yield session
    app.dependency_overrides[get_session] = override
    os.environ.update({"AUTH_USERNAME": "test-user", "AUTH_PASSWORD_HASH": PasswordHasher().hash("test-password"), "AUTH_SECRET_KEY": "test-secret-key-that-is-long-enough-12345"})
    with TestClient(app) as client:
        client.post("/login", json={"username": "test-user", "password": "test-password"})
        yield client, tmp_path / "auth.db"
    app.dependency_overrides.pop(get_session, None)
    engine.dispose()
