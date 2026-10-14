"""Database engine, session factory, and schema initialization helpers."""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./media_recommendations.db")


def create_database_engine(database_url: str = DATABASE_URL) -> Engine:
    """Create an engine configured for SQLite, including foreign-key support."""
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


engine = create_database_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(database_engine: Engine = engine) -> None:
    """Create all tables declared by the application's ORM models."""
    # Importing here avoids a circular import while ensuring model metadata exists.
    from app.models import Base

    Base.metadata.create_all(bind=database_engine)


def get_session() -> Iterator[Session]:
    """Yield a request-scoped database session for FastAPI dependencies."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
