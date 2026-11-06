import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
import test_storage
from sqlalchemy import text, update
from sqlalchemy.orm import Session

from story_api.database import migrate
from story_api.jobs import JobQueue
from story_api.providers import DemoProvider, GenerationError
from story_api.schemas import StoryRequest
from story_api.storage import RunExpired, WorkflowRun, now
from story_api.worker import process_one
from story_api.workflow import generate_story

engine = test_storage.engine


def enqueue(engine):
    store = test_storage.user_store(engine)
    story_id, run_id, _ = store.start(StoryRequest(**test_storage.REQUEST), queued=True)
    return store, story_id, run_id


def test_queue_survives_reconnection_and_only_one_worker_claims(engine):
    store, story_id, _ = enqueue(engine)
    engine.dispose()
    queue = JobQueue(engine)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: queue.claim(), range(2)))
    assert sum(job is not None for job in claims) == 1
    assert store.get(story_id)["latest_run"]["attempt"] == 1


def test_duplicate_regeneration_reuses_active_job(engine):
    store, story_id, run_id = enqueue(engine)
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: store.start(story_id=story_id, queued=True)[1], range(2)))
    assert ids == [run_id, run_id]
    assert len(store.runs(story_id, 20, 0)) == 1


def test_expired_lease_is_reclaimed_and_stale_worker_cannot_write(engine):
    store, story_id, run_id = enqueue(engine)
    queue = JobQueue(engine)
    old = queue.claim()
    with engine.begin() as connection:
        connection.execute(
            update(WorkflowRun)
            .where(WorkflowRun.id == run_id)
            .values(expires_at=now() - timedelta(seconds=1))
        )
    assert store.get(story_id)["latest_run"]["status"] == "running"
    new = queue.claim()
    assert new.run_id == old.run_id and new.token != old.token and new.attempt == 2
    with pytest.raises(RunExpired):
        queue.progress(old, "writing")
    with pytest.raises(RunExpired):
        queue.heartbeat(old)
    result = asyncio.run(generate_story(old.request, DemoProvider()))
    with pytest.raises(RunExpired):
        store.finish(run_id, result, lease_token=old.token)
    queue.fail(old, "provider_error")
    queue.heartbeat(new)
    store.finish(run_id, result, lease_token=new.token)
    assert store.get(story_id)["latest_run"]["status"] == "completed"


def test_retry_backoff_and_attempt_limit(engine):
    store, story_id, run_id = enqueue(engine)
    queue = JobQueue(engine)
    provider = DemoProvider()
    provider.generate = AsyncMock(side_effect=GenerationError("provider_timeout", "private", 504))
    for attempt in range(1, 4):
        assert asyncio.run(process_one(queue, lambda: provider))
        run = store.get(story_id)["latest_run"]
        assert run["attempt"] == attempt
        assert run["status"] == ("queued" if attempt < 3 else "failed")
        assert queue.claim() is None
        with engine.begin() as connection:
            connection.execute(
                update(WorkflowRun)
                .where(WorkflowRun.id == run_id)
                .values(available_at=now() - timedelta(seconds=1))
            )
    assert provider.generate.await_count == 3


def test_abandoned_last_attempt_becomes_terminal(engine):
    store, story_id, run_id = enqueue(engine)
    queue = JobQueue(engine)
    for attempt in range(3):
        assert queue.claim().attempt == attempt + 1
        with engine.begin() as connection:
            connection.execute(
                update(WorkflowRun)
                .where(WorkflowRun.id == run_id)
                .values(expires_at=now() - timedelta(seconds=1))
            )
    assert queue.claim() is None
    run = store.get(story_id)["latest_run"]
    assert run["status"] == "failed" and run["error_code"] == "worker_interrupted"


def test_worker_records_real_graph_progress_and_final_output(engine, monkeypatch):
    store, story_id, _ = enqueue(engine)
    queue = JobQueue(engine)
    observed = []
    original = queue.progress

    def progress(job, stage):
        original(job, stage)
        observed.append(store.get(story_id)["latest_run"]["stage"])

    monkeypatch.setattr(queue, "progress", progress)
    assert asyncio.run(process_one(queue, DemoProvider))
    assert observed == [
        "planning",
        "writing",
        "evaluating",
        "revising",
        "final_evaluation",
        "saving",
    ]
    run = store.get(story_id)["latest_run"]
    assert run["stage"] == run["status"] == "completed"
    assert run["output"]["run_id"] == run["id"]
    assert "lease_token" not in run


def test_v2_migration_preserves_existing_output(engine):
    store, story_id, run_id = enqueue(engine)
    asyncio.run(process_one(JobQueue(engine), DemoProvider))
    before = store.get(story_id)
    with engine.begin() as connection:
        connection.execute(text("DROP INDEX ix_workflow_queue"))
        for column in ("background", "stage", "attempt", "lease_token", "available_at"):
            connection.execute(text(f"ALTER TABLE workflow_runs DROP COLUMN {column}"))
        connection.execute(text("DELETE FROM story_schema_version"))
        connection.execute(text("INSERT INTO story_schema_version VALUES (2)"))
    migrate(engine)
    migrate(engine)
    assert store.get(story_id)["latest_run"]["output"] == before["latest_run"]["output"]
    with Session(engine) as session:
        assert session.get(WorkflowRun, run_id).background is False


def test_worker_shutdown_closes_provider_and_leaves_recoverable_job(engine):
    store, story_id, run_id = enqueue(engine)
    queue = JobQueue(engine)
    provider = DemoProvider()
    provider.close = AsyncMock()

    async def shutdown_during_model_call():
        entered = asyncio.Event()

        async def blocked(*args):
            entered.set()
            await asyncio.Event().wait()

        provider.generate = blocked
        task = asyncio.create_task(process_one(queue, lambda: provider))
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(shutdown_during_model_call())
    provider.close.assert_awaited_once()
    assert store.get(story_id)["latest_run"]["status"] == "running"
    with engine.begin() as connection:
        connection.execute(
            update(WorkflowRun)
            .where(WorkflowRun.id == run_id)
            .values(expires_at=now() - timedelta(seconds=1))
        )
    assert asyncio.run(process_one(queue, DemoProvider))
    run = store.get(story_id)["latest_run"]
    assert run["status"] == "completed" and run["attempt"] == 2
