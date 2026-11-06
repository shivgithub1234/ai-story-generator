"""Real PostgreSQL tests. Each test owns a uniquely named schema, never existing tables."""

import os
from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.orm import Session

from story_api import main
from story_api.auth import Identity, resolve_user
from story_api.database import migrate
from story_api.providers import DemoProvider, GenerationError
from story_api.saved_routes import get_store
from story_api.storage import Evaluation, StoryDraft, StoryStore, WorkflowRun, now

REQUEST = {
    "premise": "A detective finds a letter predicting a mysterious theft.",
    "genre": "mystery",
}


def user_store(engine):
    user = resolve_user(engine, Identity("https://test.invalid", "storage-test-user"))
    return StoryStore(engine, user.id)


@pytest.fixture
def engine():
    url = os.getenv("STORY_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set STORY_TEST_DATABASE_URL to run real PostgreSQL integration tests")
    schema = "test_story_" + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        migrate(engine)
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def client(engine, monkeypatch):
    monkeypatch.setattr(main, "create_provider", DemoProvider)
    main.app.dependency_overrides[get_store] = lambda: user_store(engine)
    try:
        with TestClient(main.app) as client:
            yield client
    finally:
        main.app.dependency_overrides.clear()


def test_save_reopen_and_retain_both_drafts_and_evaluations(client, engine):
    response = client.post("/api/stories", json=REQUEST)
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved["latest_run"]["status"] == "completed"
    assert saved["latest_run"]["id"] == saved["latest_run"]["output"]["run_id"]
    # Discard pooled connections, then read through a new repository instance.
    engine.dispose()
    reopened = user_store(engine).get(saved["id"])
    assert reopened["latest_run"]["output"] == saved["latest_run"]["output"]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(StoryDraft)) == 2
        assert session.scalar(select(func.count()).select_from(Evaluation)) == 2
    assert client.get("/api/stories").json()[0]["id"] == saved["id"]


def test_new_runs_preserve_history_and_edits_are_versioned(client):
    story = client.post("/api/stories", json=REQUEST).json()
    path = f"/api/stories/{story['id']}"
    changed = client.patch(
        path,
        json={
            "expected_version": 1,
            "title": "My story",
            "edited_text": "My manual edit",
        },
    )
    assert changed.status_code == 200
    assert changed.json()["version"] == 2
    assert changed.json()["edits_evaluated"] is False
    assert client.patch(path, json={"expected_version": 1, "title": "Stale"}).status_code == 409
    assert client.post(path + "/runs").status_code == 201
    runs = client.get(path + "/runs").json()
    assert len(runs) == 2
    assert len({run["id"] for run in runs}) == 2
    assert client.get(path).json()["edited_text"] == "My manual edit"
    assert len(client.get(path + "/runs?limit=1&offset=1").json()) == 1


def test_model_failure_is_saved_with_safe_error_code(client, monkeypatch):
    provider = DemoProvider()
    provider.generate = AsyncMock(side_effect=GenerationError("provider_timeout", "Timed out", 504))
    provider.close = AsyncMock()
    monkeypatch.setattr(main, "create_provider", lambda: provider)
    response = client.post("/api/stories", json=REQUEST)
    assert response.status_code == 504
    detail = response.json()["detail"]
    story = client.get(f"/api/stories/{detail['story_id']}").json()
    assert story["latest_run"]["status"] == "failed"
    assert story["latest_run"]["error_code"] == "provider_timeout"
    assert story["latest_run"]["output"] is None
    provider.close.assert_awaited_once()


def test_interrupted_run_is_expired_on_read(client, engine):
    from story_api.schemas import StoryRequest

    story_id, run_id, _ = user_store(engine).start(StoryRequest(**REQUEST))
    with engine.begin() as connection:
        connection.execute(
            update(WorkflowRun)
            .where(WorkflowRun.id == run_id)
            .values(expires_at=now() - timedelta(seconds=1))
        )
    result = client.get(f"/api/stories/{story_id}").json()
    assert result["latest_run"]["status"] == "failed"
    assert result["latest_run"]["error_code"] == "run_interrupted"


def test_validation_missing_story_and_idempotent_migration(client, engine):
    migrate(engine)
    assert client.get(f"/api/stories/{uuid4()}").status_code == 404
    assert client.get("/api/stories/not-a-uuid").status_code == 422
    assert client.get("/api/stories?limit=1000").status_code == 422
    assert client.post("/api/stories", json={}).status_code == 422
    story = client.post("/api/stories", json=REQUEST).json()
    assert (
        client.patch(f"/api/stories/{story['id']}", json={"expected_version": 1}).status_code == 422
    )


def test_atomic_completion_rollback(client, engine, monkeypatch):
    from sqlalchemy import event

    def reject_report(*args):
        raise RuntimeError("simulated evaluation insert failure")

    event.listen(Evaluation, "before_insert", reject_report)
    try:
        with pytest.raises(RuntimeError, match="simulated"):
            client.post("/api/stories", json=REQUEST)
    finally:
        event.remove(Evaluation, "before_insert", reject_report)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(StoryDraft)) == 0
        assert session.scalar(select(func.count()).select_from(Evaluation)) == 0
        run = session.scalar(select(WorkflowRun))
        assert run.status == "failed"
        assert run.output is None
