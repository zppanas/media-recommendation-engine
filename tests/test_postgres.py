"""Opt-in PostgreSQL compatibility tests.

Run with POSTGRES_TEST_URL pointing at a disposable database. These tests never
fall back to SQLite: without that variable they are explicitly skipped.
"""
import os
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session
from app.models import Media, MediaType, Tag, MediaTag

POSTGRES_URL = os.getenv("POSTGRES_TEST_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="POSTGRES_TEST_URL is not configured")


def test_postgres_fresh_migrations_constraints_and_foreign_keys():
    engine = create_engine(POSTGRES_URL)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", POSTGRES_URL.replace("%", "%%"))
    command.upgrade(config, "head")
    try:
        names = set(inspect(engine).get_table_names())
        assert {"media", "tags", "media_tags", "library_entries", "media_logs", "user_feedback"} <= names
        assert {"mediatype", "feedbacktype", "librarystatus", "activitytype"} <= {
            enum["name"] for enum in inspect(engine).get_enums()
        }
        assert {"ix_library_entries_status", "ix_media_logs_media_logged_at"} <= {i["name"] for i in inspect(engine).get_indexes("library_entries")} | {i["name"] for i in inspect(engine).get_indexes("media_logs")}
        assert any(f["name"] == "uq_library_entries_media_id" for f in inspect(engine).get_unique_constraints("library_entries"))
        assert any(f["referred_table"] == "media" for f in inspect(engine).get_foreign_keys("library_entries"))
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO media (title, media_type, created_at, updated_at) VALUES ('x', 'BOOK', now(), now())"))
            with pytest.raises(Exception):
                connection.execute(text("INSERT INTO library_entries (media_id, status, added_at) VALUES (999999, 'WANT_TO_TRY', now())"))
    finally:
        command.downgrade(config, "base")
        engine.dispose()


def test_postgres_initial_revision_upgrades_and_core_crud():
    engine = create_engine(POSTGRES_URL)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", POSTGRES_URL.replace("%", "%%"))
    command.upgrade(config, "0001_initial")
    try:
        assert "creator" not in {column["name"] for column in inspect(engine).get_columns("media")}
        command.upgrade(config, "head")
        assert "creator" in {column["name"] for column in inspect(engine).get_columns("media")}
        with Session(engine) as session:
            media = Media(title="Dune", creator="Frank Herbert", media_type=MediaType.BOOK)
            tag = Tag(normalized_name="science fiction")
            session.add_all([media, tag])
            session.flush()
            session.add(MediaTag(media=media, tag=tag, strength=5))
            session.commit()
            saved = session.scalar(select(Media).where(Media.title == "Dune"))
            assert saved is not None and saved.creator == "Frank Herbert"
            assert len(saved.tag_links) == 1
    finally:
        command.downgrade(config, "base")
        engine.dispose()
