from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

def test_alembic_upgrade_fresh_temporary_database(tmp_path):
    db = tmp_path / "migration.db"
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{db}")
    tables = set(inspect(engine).get_table_names())
    engine.dispose()
    assert {"media", "library_entries", "media_logs", "tags", "media_tags", "user_feedback", "alembic_version"} <= tables
from pathlib import Path
