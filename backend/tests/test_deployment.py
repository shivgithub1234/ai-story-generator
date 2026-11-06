import pytest
import test_storage
from fastapi.testclient import TestClient
from sqlalchemy import text

from story_api import main
from story_api.preflight import DeploymentConfigurationError, validate_runtime

engine = test_storage.engine


@pytest.fixture
def production(monkeypatch):
    settings = {
        "STORY_ENV": "production",
        "STORY_PROVIDER": "gemini",
        "GEMINI_API_KEY": "test-only",
        "GEMINI_MODEL": "test-model",
        "AUTH_ISSUER": "https://auth.example.com",
        "AUTH_AUDIENCE": "story-api",
        "AUTH_JWKS_URL": "https://auth.example.com/.well-known/jwks.json",
        "AUTH_AUTHORIZED_PARTIES": "https://stories.example.com",
        "DATABASE_URL": "postgresql://test:secret@example.com/story?sslmode=require",
        "STORY_ENABLE_UNMETERED_DEV_ENDPOINT": "false",
        "STORY_REQUESTS_PER_24H": "10",
        "STORY_MAX_ACTIVE_JOBS": "2",
    }
    for key, value in settings.items():
        monkeypatch.setenv(key, value)


def test_production_settings_pass(production):
    validate_runtime()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("STORY_ENABLE_UNMETERED_DEV_ENDPOINT", "true"),
        ("STORY_PROVIDER", "demo"),
        ("GEMINI_API_KEY", ""),
        ("AUTH_AUTHORIZED_PARTIES", "http://localhost:3000"),
        ("AUTH_ISSUER", "https://test.clerk.accounts.dev"),
        ("DATABASE_URL", "postgresql://test:secret@example.com/story"),
        ("STORY_REQUESTS_PER_24H", "0"),
    ],
)
def test_production_rejects_unsafe_settings(production, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(DeploymentConfigurationError) as error:
        validate_runtime()
    assert "secret" not in str(error.value)


def test_readiness_requires_schema_and_liveness_does_not(engine, monkeypatch):
    monkeypatch.setattr(main, "get_engine", lambda: engine)
    with TestClient(main.app) as client:
        assert client.get("/ready").json() == {"status": "ready"}
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM story_schema_version"))
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "not_ready"}
        assert client.get("/health").status_code == 200


def test_readiness_hides_connection_details(monkeypatch):
    from sqlalchemy.exc import OperationalError

    def unavailable():
        raise OperationalError("secret database host", {}, Exception("password"))

    monkeypatch.setattr(main, "get_engine", unavailable)
    with TestClient(main.app) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
