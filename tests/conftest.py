import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient


TEST_PASSWORD = "correct horse battery staple"
TEST_PASSWORD_HASH = PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1).hash(TEST_PASSWORD)


@pytest.fixture()
def unauth_client(tmp_path, monkeypatch):
    monkeypatch.setenv("AYQM_DATABASE_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("AYQM_UPLOAD_ROOT", str(tmp_path / "uploads"))
    monkeypatch.setenv("AYQM_EPISODE_ROOT", str(tmp_path / "episodes"))
    monkeypatch.setenv("AYQM_ADMIN_PASSWORD_HASH", TEST_PASSWORD_HASH)
    monkeypatch.setenv("AYQM_SESSION_SECRET", "test-session-secret-with-enough-entropy")
    monkeypatch.setenv("AYQM_SESSION_COOKIE_SECURE", "false")

    from backend.app.config import get_settings
    from backend.app.main import create_app

    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


@pytest.fixture()
def client(unauth_client):
    response = unauth_client.post("/auth/login", json={"password": TEST_PASSWORD})
    assert response.status_code == 200
    yield unauth_client
