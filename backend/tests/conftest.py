import pytest

from story_api.auth import Identity, verified_identity
from story_api.main import app


@pytest.fixture
def signed_in(monkeypatch):
    """Existing model tests focus on generation; auth tests verify real signed tokens."""
    monkeypatch.setenv("STORY_ENABLE_UNMETERED_DEV_ENDPOINT", "true")
    app.dependency_overrides[verified_identity] = lambda: Identity(
        "https://test.invalid", "test-user"
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(verified_identity, None)
