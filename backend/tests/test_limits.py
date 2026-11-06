from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
import test_storage
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from story_api.auth import Identity, resolve_user
from story_api.limits import UsageConfigurationError, UsageLimitExceeded, get_limits
from story_api.main import app
from story_api.schemas import StoryRequest
from story_api.storage import StoryProject, StoryStore, WorkflowRun, now

engine = test_storage.engine
client = test_storage.client
REQUEST = StoryRequest(**test_storage.REQUEST)


def test_active_limit_rejects_without_leaving_empty_project(client, engine, monkeypatch):
    monkeypatch.setenv("STORY_MAX_ACTIVE_JOBS", "1")
    first = client.post("/api/stories", json=REQUEST.model_dump()).json()
    rejected = client.post("/api/stories", json=REQUEST.model_dump())
    assert rejected.status_code == 429
    assert rejected.json()["detail"]["code"] == "active_job_limit"
    assert client.get("/api/stories/usage").json()["used"] == 1
    assert (
        client.post(f"/api/stories/{first['id']}/runs").json()["latest_run"]["id"]
        == first["latest_run"]["id"]
    )
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(StoryProject)) == 1


def test_daily_limit_counts_failed_runs_but_not_retries_and_recovers(engine, monkeypatch):
    monkeypatch.setenv("STORY_REQUESTS_PER_24H", "1")
    store = test_storage.user_store(engine)
    story, run, _ = store.start(REQUEST, queued=True)
    with engine.begin() as connection:
        connection.execute(
            update(WorkflowRun).where(WorkflowRun.id == run).values(status="failed", attempt=3)
        )
    assert store.usage()["used"] == 1 and store.usage()["active_jobs"] == 0
    with pytest.raises(UsageLimitExceeded) as error:
        store.start(story_id=story, queued=True)
    assert error.value.code == "daily_usage_limit"
    assert error.value.usage["next_credit_at"] is not None
    with engine.begin() as connection:
        connection.execute(
            update(WorkflowRun)
            .where(WorkflowRun.id == run)
            .values(started_at=now() - timedelta(hours=24, seconds=1))
        )
    assert store.usage()["remaining"] == 1
    store.start(story_id=story, queued=True)
    assert store.usage()["used"] == 1


@pytest.mark.parametrize("setting", ["STORY_REQUESTS_PER_24H", "STORY_MAX_ACTIVE_JOBS"])
def test_simultaneous_submissions_cannot_overrun_last_slot(engine, monkeypatch, setting):
    monkeypatch.setenv(setting, "1")
    store = test_storage.user_store(engine)

    def submit(_):
        try:
            store.start(REQUEST, queued=True)
            return "accepted"
        except UsageLimitExceeded:
            return "rejected"

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(submit, range(4)))
    assert results.count("accepted") == 1
    assert store.usage()["used"] == 1


def test_user_allowances_are_independent_and_persistent(engine, monkeypatch):
    monkeypatch.setenv("STORY_REQUESTS_PER_24H", "1")
    a = test_storage.user_store(engine)
    b = StoryStore(engine, resolve_user(engine, Identity("https://test.invalid", "bob")).id)
    a.start(REQUEST, queued=True)
    assert b.usage()["remaining"] == 1
    b.start(REQUEST, queued=True)
    engine.dispose()
    assert StoryStore(engine, a.owner_id).usage()["remaining"] == 0
    assert b.usage()["used"] == 1


@pytest.mark.parametrize("value", ["0", "-1", "oops", "10001"])
def test_invalid_limits_fail_closed(monkeypatch, value):
    monkeypatch.setenv("STORY_REQUESTS_PER_24H", value)
    with pytest.raises(UsageConfigurationError):
        get_limits()


def test_legacy_endpoint_cannot_bypass_limits_by_default(signed_in, monkeypatch):
    monkeypatch.setenv("STORY_ENABLE_UNMETERED_DEV_ENDPOINT", "false")
    with TestClient(app) as client:
        response = client.post("/api/stories/generate", json=REQUEST.model_dump())
    assert response.status_code == 410
    assert response.json()["detail"]["code"] == "use_saved_generation"
