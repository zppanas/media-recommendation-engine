"""Create the original schema explicitly for SQLite and PostgreSQL."""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

MT = sa.Enum("BOOK", "TV_SHOW", "MOVIE", "GAME", name="mediatype")
FT = sa.Enum("INTERESTED", "NOT_FOR_ME", "ALREADY_KNOW_IT", "GREAT_DISCOVERY", name="feedbacktype")
LS = sa.Enum("WANT_TO_TRY", "IN_PROGRESS", "COMPLETED", "ON_HOLD", "ABANDONED", name="librarystatus")
AT = sa.Enum("STARTED", "CONTINUED", "FINISHED", "REVISITED", "OTHER", name="activitytype")

def upgrade():
    bind = op.get_bind()
    op.create_table("media", sa.Column("id", sa.Integer, primary_key=True), sa.Column("title", sa.String(255), nullable=False),
        sa.Column("media_type", MT, nullable=False), sa.Column("release_year", sa.Integer), sa.Column("description", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False), sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.CheckConstraint("release_year IS NULL OR release_year BETWEEN 1000 AND 9999"))
    op.create_table("tags", sa.Column("id", sa.Integer, primary_key=True), sa.Column("normalized_name", sa.String(100), unique=True, nullable=False), sa.Column("category", sa.String(100)))
    op.create_table("user_feedback", sa.Column("id", sa.Integer, primary_key=True), sa.Column("media_id", sa.Integer, sa.ForeignKey("media.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feedback_type", FT, nullable=False), sa.Column("rating", sa.Integer), sa.Column("notes", sa.Text), sa.Column("created_at", sa.DateTime, nullable=False), sa.Column("updated_at", sa.DateTime, nullable=False), sa.CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5"))
    op.create_table("library_entries", sa.Column("id", sa.Integer, primary_key=True), sa.Column("media_id", sa.Integer, sa.ForeignKey("media.id", ondelete="CASCADE"), nullable=False), sa.Column("status", LS, nullable=False), sa.Column("priority", sa.Integer), sa.Column("added_at", sa.DateTime, nullable=False), sa.UniqueConstraint("media_id", name="uq_library_entries_media_id"))
    op.create_index("ix_library_entries_status", "library_entries", ["status"])
    op.create_table("media_logs", sa.Column("id", sa.Integer, primary_key=True), sa.Column("media_id", sa.Integer, sa.ForeignKey("media.id", ondelete="CASCADE"), nullable=False), sa.Column("activity_type", AT, nullable=False), sa.Column("start_date", sa.Date), sa.Column("finish_date", sa.Date), sa.Column("logged_at", sa.DateTime, nullable=False), sa.Column("rating", sa.Integer), sa.Column("review", sa.Text), sa.Column("private_notes", sa.Text), sa.Column("created_at", sa.DateTime, nullable=False), sa.Column("updated_at", sa.DateTime, nullable=False), sa.CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5"), sa.CheckConstraint("finish_date IS NULL OR start_date IS NULL OR finish_date >= start_date"))
    op.create_index("ix_media_logs_media_logged_at", "media_logs", ["media_id", "logged_at"])
    op.create_table("media_tags", sa.Column("media_id", sa.Integer, sa.ForeignKey("media.id", ondelete="CASCADE"), primary_key=True), sa.Column("tag_id", sa.Integer, sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True), sa.Column("strength", sa.Integer), sa.UniqueConstraint("media_id", "tag_id", name="uq_media_tags_media_id_tag_id"), sa.CheckConstraint("strength IS NULL OR strength BETWEEN 1 AND 5"))

def downgrade():
    for table in ("media_tags", "media_logs", "library_entries", "user_feedback", "tags", "media"): op.drop_table(table)
    if op.get_bind().dialect.name == "postgresql":
        for enum in (AT, LS, FT, MT): enum.drop(op.get_bind(), checkfirst=True)
