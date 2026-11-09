import asyncio

import pytest

from app.database import create_database_engine, database_url, validate_database_connection


def test_production_requires_database_url(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        database_url()


def test_postgres_url_is_normalized(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@localhost/db")
    assert database_url().startswith("postgresql+psycopg://")


def test_database_initialization_failure_is_reported(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://invalid:invalid@127.0.0.1:1/missing")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AUTH_USERNAME", "test-user")
    monkeypatch.setenv("AUTH_PASSWORD_HASH", "test-hash")
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-secret-key-that-is-long-enough-12345")
    import app.database as database
    from app.main import validate_production_auth

    monkeypatch.setattr(database, "engine", create_database_engine(database.database_url()))
    with pytest.raises(RuntimeError, match="database connection failed"):
        asyncio.run(validate_production_auth())
