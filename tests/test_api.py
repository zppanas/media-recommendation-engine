from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import sessionmaker
from app.database import create_database_engine, init_db, engine as application_engine
from app.main import app
from app.database import get_session

@pytest.fixture
def isolated_client(tmp_path):
    db = tmp_path / "api.db"
    engine = create_database_engine(f"sqlite:///{db}")
    init_db(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    def override():
        with sessions() as session: yield session
    app.dependency_overrides[get_session] = override
    with TestClient(app) as client:
        yield client, db
    app.dependency_overrides.pop(get_session, None)
    engine.dispose()

def test_media_library_and_isolation(isolated_client):
    client, db = isolated_client
    created = client.post("/media", json={"title":"Dune", "media_type":"book"})
    assert created.status_code == 201
    assert created.json()["title"] == "Dune"
    media = client.get("/media", params={"search":"dune"}).json()[0]
    assert client.get(f"/media/{media['id']}").status_code == 200
    assert client.patch(f"/media/{media['id']}", json={"title":"Dune Messiah", "media_type":"book"}).status_code == 200
    assert client.post(f"/media/{media['id']}/library", json={"status":"in_progress", "priority":2}).status_code == 201
    assert client.patch(f"/media/{media['id']}/library", json={"status":"completed"}).json()["status"] == "completed"
    assert db.exists()
    # The override points at this temporary engine; the application default remains separate.
    assert str(application_engine.url) != f"sqlite:///{db}"

def test_repeated_diary_entries_and_validation(isolated_client):
    client, _ = isolated_client
    media = client.post("/media", json={"title":"The Wire", "media_type":"tv_show"}).json()
    path = f"/media/{media['id']}/logs"
    payload = {"activity_type":"started", "start_date":"2026-01-01", "finish_date":"2026-01-02", "rating":5}
    first = client.post(path, json=payload)
    second = client.post(path, json={**payload, "activity_type":"revisited", "rating":4})
    assert first.status_code == second.status_code == 201
    entries = client.get(path)
    assert entries.status_code == 200 and len(entries.json()) == 2
    assert client.post(path, json={**payload, "rating":6}).status_code == 422
    assert client.post(path, json={**payload, "finish_date":"2025-01-01"}).status_code == 422

def test_tags_feedback_and_missing_records(isolated_client):
    client, _ = isolated_client
    assert client.get("/media/999").status_code == 404
    assert client.get("/media/999/library").status_code == 404
    assert client.get("/media/999/logs").status_code == 404
    assert client.post("/tags", json={"normalized_name":"science fiction"}).status_code == 201
    duplicate = client.post("/tags", json={"normalized_name":"science fiction"})
    assert duplicate.status_code == 409
    media = client.post("/media", json={"title":"Arrival", "media_type":"movie"}).json()
    tag = client.post("/tags", json={"normalized_name":"thoughtful"}).json()
    assert client.post(f"/media/{media['id']}/tags/{tag['id']}", params={"strength":5}).status_code == 201
    assert client.delete(f"/media/{media['id']}/tags/{tag['id']}").status_code == 204
    assert client.post(f"/media/{media['id']}/feedback", json={"feedback_type":"great_discovery"}).status_code == 201
    assert len(client.get(f"/media/{media['id']}/feedback").json()) == 1
    assert client.get(f"/media/{media['id']}/logs/999").status_code == 404

def test_dashboard_core_create_and_update_workflow(isolated_client):
    client, _ = isolated_client
    media = client.post("/media", json={
        "title": "Kindred", "media_type": "book", "release_year": 1979,
        "description": "A time-spanning novel",
    })
    assert media.status_code == 201
    mid = media.json()["id"]
    duplicate_media = client.post("/media", json={
        "title": "Kindred", "media_type": "book", "release_year": 1979,
        "description": "A time-spanning novel",
    })
    assert duplicate_media.status_code == 409
    assert client.get(f"/media/{mid}/library").status_code == 404
    assert client.post(f"/media/{mid}/library", json={"status": "want_to_try"}).status_code == 201
    assert client.post(f"/media/{mid}/library", json={"status": "completed"}).status_code == 409
    assert client.get(f"/media/{mid}/library").json()["status"] == "want_to_try"
    assert client.patch(f"/media/{mid}/library", json={"status": "in_progress"}).json()["status"] == "in_progress"
    entry = client.post(f"/media/{mid}/logs", json={
        "activity_type": "started", "start_date": "2026-10-01",
        "rating": 4, "review": "A first note",
    })
    assert entry.status_code == 201
    lid = entry.json()["id"]
    assert client.post(f"/media/{mid}/logs", json={"activity_type": "revisited"}).status_code == 201
    edited = client.patch(f"/media/{mid}/logs/{lid}", json={
        "activity_type": "finished", "rating": 5, "review": "Finished note",
    })
    assert edited.status_code == 200 and edited.json()["rating"] == 5
    assert len(client.get(f"/media/{mid}/logs").json()) == 2

def test_deletions_preserve_media_on_library_and_log_removal(isolated_client):
    client, _ = isolated_client
    media = client.post("/media", json={"title":"Keep me", "media_type":"book"}).json()
    mid = media["id"]
    client.post(f"/media/{mid}/library", json={"status":"completed"})
    log = client.post(f"/media/{mid}/logs", json={"activity_type":"finished"}).json()
    assert client.delete(f"/media/{mid}/library").status_code == 204
    assert client.get(f"/media/{mid}").status_code == 200
    assert client.get(f"/media/{mid}/logs").json()[0]["id"] == log["id"]
    assert client.delete(f"/media/{mid}/logs/{log['id']}").status_code == 204
    assert client.get(f"/media/{mid}/logs").json() == []

def test_catalog_deletion_requires_explicit_related_cleanup(isolated_client):
    client, _ = isolated_client
    media = client.post("/media", json={"title":"Delete me", "media_type":"movie"}).json()
    mid = media["id"]
    client.post(f"/media/{mid}/library", json={"status":"want_to_try"})
    client.post(f"/media/{mid}/logs", json={"activity_type":"started"})
    summary = client.get(f"/media/{mid}/deletion-summary").json()
    assert summary["library_entries"] == 1 and summary["diary_entries"] == 1
    assert client.delete(f"/media/{mid}").status_code == 409
    assert client.delete(f"/media/{mid}?purge_related=true").status_code == 204
    assert client.get(f"/media/{mid}").status_code == 404
    assert client.get(f"/media/{mid}/logs").status_code == 404
