"""add creator to media records"""
from alembic import op
import sqlalchemy as sa

revision = "0002_add_creator"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade():
    # The initial migration creates from current ORM metadata in this project;
    # guard this migration so fresh databases and older deployed databases both
    # upgrade cleanly.
    if "creator" not in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("media")}:
        op.add_column("media", sa.Column("creator", sa.String(length=255), nullable=True))

def downgrade():
    if "creator" in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("media")}:
        op.drop_column("media", "creator")
