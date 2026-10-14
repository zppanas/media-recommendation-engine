from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import create_database_engine, init_db
from app.models import FeedbackType, Media, MediaTag, MediaType, Tag, UserFeedback


def test_init_db_creates_all_tables(tmp_path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)

    assert {"media", "tags", "media_tags", "user_feedback"}.issubset(inspect(engine).get_table_names())


def test_create_and_retrieve_media(tmp_path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)

    with Session(engine) as session:
        session.add(Media(title="  Dune  ", media_type=MediaType.BOOK, release_year=1965))
        session.commit()

        media = session.scalar(select(Media).where(Media.title == "Dune"))
        assert media is not None
        assert media.media_type is MediaType.BOOK
        assert media.release_year == 1965


def test_assigning_a_tag_prevents_duplicate_attachment(tmp_path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)

    with Session(engine) as session:
        media = Media(title="Dune", media_type=MediaType.BOOK)
        tag = Tag(normalized_name="science fiction", category="genre")
        session.add_all([media, tag])
        session.flush()
        session.add(MediaTag(media=media, tag=tag, strength=5))
        session.commit()

        assert session.scalar(select(MediaTag).where(MediaTag.media_id == media.id)).strength == 5
        session.add(MediaTag(media_id=media.id, tag_id=tag.id))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError("A duplicate media/tag association should fail.")


def test_save_feedback(tmp_path):
    engine = create_database_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)

    with Session(engine) as session:
        media = Media(title="Spirited Away", media_type=MediaType.MOVIE)
        feedback = UserFeedback(
            media=media,
            feedback_type=FeedbackType.LIKED,
            rating=5,
            notes="Beautiful animation.",
        )
        session.add(feedback)
        session.commit()

        saved_feedback = session.scalar(select(UserFeedback))
        assert saved_feedback is not None
        assert saved_feedback.media.title == "Spirited Away"
        assert saved_feedback.rating == 5
