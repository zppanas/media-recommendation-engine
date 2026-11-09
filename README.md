# Personal Media Recommendation Engine

An incremental personal media catalogue, library, diary, and recommendation-feedback app for books, TV shows, movies, and games.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Apply the schema through Alembic (default: `media_recommendations.db`; this does not delete or overwrite existing data):

```bash
alembic upgrade head
```

Set `DATABASE_URL` to point the application at another SQLAlchemy-compatible database URL. For example:

```bash
DATABASE_URL=sqlite:///./my_media.db python -m app.init_db
```

Run the development server:

```bash
uvicorn app.main:app --reload
```

Run tests:

```bash
pytest
```

Configure the single account with deployment secrets; do not commit them. Generate a hash with `python -c "from argon2 import PasswordHasher; print(PasswordHasher().hash(input('Password: ')))"`, then set `AUTH_USERNAME`, `AUTH_PASSWORD_HASH`, and a random `AUTH_SECRET_KEY` of at least 32 characters. Set `ENVIRONMENT=production` to enable secure cookies. `/health`, `/login` (GET/POST), and login assets are public; the dashboard, all application APIs, `/docs`, `/redoc`, and the OpenAPI schema require authentication. Unsafe cookie-authenticated requests require the `X-CSRF-Token` header matching the CSRF cookie.

PostgreSQL uses `psycopg` and accepts `postgresql://` or `postgres://` URLs, which are normalized to the psycopg SQLAlchemy dialect. In production/staging, `DATABASE_URL` is required and the application verifies the connection during startup; schema changes must be applied with Alembic. Set `POSTGRES_TEST_URL` to a disposable PostgreSQL database to run the opt-in PostgreSQL integration tests.

The integration tests create a separate temporary SQLite database for each API scenario by overriding the session dependency; they never use or reset the default local database. Migration coverage runs `alembic upgrade head` against a fresh temporary database.

The API is available at `http://127.0.0.1:8000`; interactive OpenAPI documentation is at `/docs`. Set `DATABASE_URL` for another SQLAlchemy URL, for example `DATABASE_URL=sqlite:///./my_media.db alembic upgrade head`.

## Run the personal dashboard

After applying the migration, start the same development server:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000/app/](http://127.0.0.1:8000/app/) for the plain HTML/CSS/JavaScript dashboard. The dashboard separates the shared Catalog from My Library: Catalog shows every media record, while My Library shows only records with a library entry. My Diary and Media Details remain available for catalog-only works. The dashboard calls the FastAPI endpoints directly; it does not keep a second catalog in browser storage. The frontend files live in `frontend/` and are mounted at `/app`.

The current API does not provide a GET endpoint for tags or a combined media-detail response. The detail view therefore loads metadata, library state, and diary entries from their existing endpoints. Tag display/attachment UI is intentionally limited until the API can safely list tags and current attachments.

## Project structure

- `app/main.py` — FastAPI endpoints and Pydantic request/response schemas.
- `app/database.py` — database engine/session setup and `init_db()`.
- `app/models.py` — SQLAlchemy entities and database-level constraints.
- `alembic/` and `alembic.ini` — explicit schema migration configuration and revisions.
- `tests/test_database.py` — isolated SQLite database tests.
- `frontend/` — static personal media dashboard.

## Data model

- `Media` is a catalogue item with a title, one of four media types, optional release year/description, and creation/update timestamps.
- `Tag` is a reusable, uniquely named normalized label, with an optional category such as `genre` or `mood`.
- `MediaTag` associates a media item with a tag and can record strength from 1 to 5. Its composite primary key prevents duplicate attachments.
- `UserFeedback` records a feedback event for a media item, with a feedback type, optional 1–5 rating and notes, plus timestamps.
- `LibraryEntry` is an optional, unique personal library record per work, with status, priority, and added time.
- `MediaLog` is a repeatable dated diary entry with activity, dates, rating, review, private notes, and timestamps.

## API outline

Use `POST/GET/PATCH/DELETE /media` for catalogue records and search filters (`search`, `media_type`, `release_year`). Catalog deletion requires explicit `purge_related=true` when associated records exist and permanently removes those associations and diary entries. `GET /library` returns only media with a library entry and accepts the same filters. Use `/media/{id}/library` and `/media/{id}/logs` for library/diary operations; their DELETE operations remove only the selected association or entry. Use `/tags`, `/media/{id}/tags/{tag_id}`, and `/media/{id}/feedback` for tags and recommendation feedback. Ratings and diary dates are validated by both Pydantic and database constraints.

## Initial design choices to revisit

- `UserFeedback` keeps feedback as an event history; multiple entries for the same media item are allowed. We can later decide whether the product instead needs one current feedback record per media item.
- Tags store only their normalized form. If a display spelling (for example, `Sci-Fi`) matters later, add a separate display-name column.
- Ratings and tag strength use a simple 1–5 integer scale, which is easy to query but should be confirmed before user-facing work begins.
