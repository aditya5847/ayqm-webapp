import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AYQM_DATABASE_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("AYQM_UPLOAD_ROOT", str(tmp_path / "uploads"))
    monkeypatch.setenv("AYQM_EPISODE_ROOT", str(tmp_path / "episodes"))

    from backend.app.config import get_settings
    from backend.app.main import create_app

    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()

