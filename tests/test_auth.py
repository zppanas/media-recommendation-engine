import pytest


def test_public_health_but_protected_application_routes(isolated_client):
    client, _ = isolated_client
    client.cookies.clear()
    assert client.get("/health").status_code == 200
    assert client.get("/app/", follow_redirects=False).status_code == 307
    for path in ("/media", "/library", "/openapi.json", "/docs"):
        assert client.get(path).status_code == 401


def test_login_rejects_invalid_credentials_and_logout_invalidates_session(isolated_client):
    client, _ = isolated_client
    client.cookies.clear()
    assert client.post("/login", json={"username": "test-user", "password": "wrong"}).status_code == 401
    assert client.post("/login", json={"username": "test-user", "password": "test-password"}).status_code == 200
    assert client.get("/media").status_code == 200
    csrf = client.cookies["media_csrf"]
    assert client.post("/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert client.get("/media").status_code == 401


def test_state_changes_require_csrf(isolated_client):
    client, _ = isolated_client
    assert client.post("/media", json={"title": "No CSRF", "media_type": "book"}, headers={"X-CSRF-Token": "bad"}).status_code == 403


@pytest.mark.parametrize("method,path", [
    ("delete", "/media/1"),
    ("delete", "/media/1/library"),
    ("delete", "/media/1/logs/1"),
    ("delete", "/media/1/tags/1"),
])
def test_every_destructive_endpoint_requires_csrf(isolated_client, method, path):
    client, _ = isolated_client
    assert getattr(client, method)(path).status_code == 403
