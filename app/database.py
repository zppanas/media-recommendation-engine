"""Database engine, session factory, and schema initialization helpers."""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

def database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if not value:
        if os.getenv("ENVIRONMENT", "development").lower() in {"production", "staging"}:
            raise RuntimeError("DATABASE_URL is required in production/staging")
        return "sqlite:///./media_recommendations.db"
    # Heroku-style URLs use the deprecated SQLAlchemy scheme name.
    if value.startswith("postgres://"):
        value = "postgresql+psycopg://" + value[len("postgres://"):]
    elif value.startswith("postgresql://"):
        value = "postgresql+psycopg://" + value[len("postgresql://"):]
    return value


def create_database_engine(database_url: str | None = None) -> Engine:
    """Create an engine configured for SQLite, including foreign-key support."""
    database_url = database_url or database_url_from_environment()
    is_sqlite = database_url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    engine = create_engine(database_url, connect_args=connect_args)

    if is_sqlite:

        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def validate_database_connection() -> None:
    """Fail startup with the actual connection error, rather than on first request."""
    with engine.connect():
        pass


def database_url_from_environment() -> str:
    return database_url()


engine = create_database_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(database_engine: Engine = engine) -> None:
    """Create all tables declared by the application's ORM models."""
    # Importing here avoids a circular import while ensuring model metadata exists.
    from app.models import Base

    if os.getenv("ENVIRONMENT", "development").lower() in {"production", "staging"}:
        raise RuntimeError("init_db() is a development helper; run Alembic migrations in production")
    Base.metadata.create_all(bind=database_engine)


def get_session() -> Iterator[Session]:
    """Yield a request-scoped database session for FastAPI dependencies."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
