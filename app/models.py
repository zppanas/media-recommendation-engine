"""SQLAlchemy models for the media catalogue and personal feedback."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from sqlalchemy import CheckConstraint, Date, DateTime, Enum as SqlEnum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, validates


class Base(DeclarativeBase):
    pass


class MediaType(str, Enum):
    BOOK = "book"
    TV_SHOW = "tv_show"
    MOVIE = "movie"
    GAME = "game"


class FeedbackType(str, Enum):
    INTERESTED = "interested"
    NOT_FOR_ME = "not_for_me"
    ALREADY_KNOW_IT = "already_know_it"
    GREAT_DISCOVERY = "great_discovery"
    # Backward-compatible names from the original milestone.
    LIKED = "great_discovery"
    DISLIKED = "not_for_me"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class Media(TimestampMixin, Base):
    __tablename__ = "media"
    __table_args__ = (CheckConstraint("release_year IS NULL OR release_year BETWEEN 1000 AND 9999"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    creator: Mapped[Optional[str]] = mapped_column(String(255))
    media_type: Mapped[MediaType] = mapped_column(SqlEnum(MediaType), nullable=False)
    release_year: Mapped[Optional[int]] = mapped_column(Integer)
    description: Mapped[Optional[str]] = mapped_column(Text)

    tag_links: Mapped[List["MediaTag"]] = relationship(back_populates="media", cascade="all, delete-orphan")
    feedback: Mapped[List["UserFeedback"]] = relationship(back_populates="media", cascade="all, delete-orphan")
    library_entry: Mapped[Optional["LibraryEntry"]] = relationship(back_populates="media", cascade="all, delete-orphan", uselist=False)
    logs: Mapped[List["MediaLog"]] = relationship(back_populates="media", cascade="all, delete-orphan")

    @validates("title")
    def validate_title(self, _: str, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Media title cannot be empty.")
        return value


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    normalized_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(100))

    media_links: Mapped[List["MediaTag"]] = relationship(back_populates="tag", cascade="all, delete-orphan")

    @validates("normalized_name")
    def validate_normalized_name(self, _: str, value: str) -> str:
        normalized = " ".join(value.split()).lower()
        if not normalized:
            raise ValueError("Tag normalized name cannot be empty.")
        if value != normalized:
            raise ValueError("Tag normalized name must be lowercase with single spaces.")
        return normalized


class MediaTag(Base):
    __tablename__ = "media_tags"
    __table_args__ = (
        UniqueConstraint("media_id", "tag_id", name="uq_media_tags_media_id_tag_id"),
        CheckConstraint("strength IS NULL OR strength BETWEEN 1 AND 5"),
    )

    media_id: Mapped[int] = mapped_column(ForeignKey("media.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
    strength: Mapped[Optional[int]] = mapped_column(Integer)

    media: Mapped[Media] = relationship(back_populates="tag_links")
    tag: Mapped[Tag] = relationship(back_populates="media_links")


class UserFeedback(TimestampMixin, Base):
    __tablename__ = "user_feedback"
    __table_args__ = (CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    media_id: Mapped[int] = mapped_column(ForeignKey("media.id", ondelete="CASCADE"), nullable=False)
    feedback_type: Mapped[FeedbackType] = mapped_column(SqlEnum(FeedbackType), nullable=False)
    rating: Mapped[Optional[int]] = mapped_column(Integer)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    media: Mapped[Media] = relationship(back_populates="feedback")


class LibraryStatus(str, Enum):
    WANT_TO_TRY = "want_to_try"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ON_HOLD = "on_hold"
    ABANDONED = "abandoned"


class ActivityType(str, Enum):
    STARTED = "started"
    CONTINUED = "continued"
    FINISHED = "finished"
    REVISITED = "revisited"
    OTHER = "other"


class LibraryEntry(Base):
    __tablename__ = "library_entries"
    __table_args__ = (UniqueConstraint("media_id", name="uq_library_entries_media_id"), Index("ix_library_entries_status", "status"))

    id: Mapped[int] = mapped_column(primary_key=True)
    media_id: Mapped[int] = mapped_column(ForeignKey("media.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[LibraryStatus] = mapped_column(SqlEnum(LibraryStatus), nullable=False, default=LibraryStatus.WANT_TO_TRY)
    priority: Mapped[Optional[int]] = mapped_column(Integer)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    media: Mapped[Media] = relationship(back_populates="library_entry")


class MediaLog(TimestampMixin, Base):
    __tablename__ = "media_logs"
    __table_args__ = (
        CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5"),
        CheckConstraint("finish_date IS NULL OR start_date IS NULL OR finish_date >= start_date"),
        Index("ix_media_logs_media_logged_at", "media_id", "logged_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    media_id: Mapped[int] = mapped_column(ForeignKey("media.id", ondelete="CASCADE"), nullable=False)
    activity_type: Mapped[ActivityType] = mapped_column(SqlEnum(ActivityType), nullable=False)
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    finish_date: Mapped[Optional[date]] = mapped_column(Date)
    logged_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    rating: Mapped[Optional[int]] = mapped_column(Integer)
    review: Mapped[Optional[str]] = mapped_column(Text)
    private_notes: Mapped[Optional[str]] = mapped_column(Text)
    media: Mapped[Media] = relationship(back_populates="logs")
