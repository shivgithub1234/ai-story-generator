"""PostgreSQL queue with short claims, renewable leases, and fenced writes."""

from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from story_api.schemas import StoryRequest
from story_api.storage import RunExpired, StoryProject, WorkflowRun, now

MAX_ATTEMPTS = 3
LEASE_SECONDS = 90
RETRYABLE = {"provider_timeout", "provider_unavailable", "provider_rate_limit", "workflow_timeout"}


@dataclass(frozen=True)
class Job:
    run_id: str
    owner_id: str
    token: str
    attempt: int
    request: StoryRequest


class JobQueue:
    def __init__(self, engine):
        self.engine = engine

    def claim(self):
        with Session(self.engine) as session, session.begin():
            # Exhausted abandoned attempts become terminal even without browser reads.
            session.execute(
                update(WorkflowRun)
                .where(
                    WorkflowRun.background.is_(True),
                    WorkflowRun.status == "running",
                    WorkflowRun.expires_at <= now(),
                    WorkflowRun.attempt >= MAX_ATTEMPTS,
                )
                .values(
                    status="failed",
                    stage="failed",
                    error_code="worker_interrupted",
                    lease_token=None,
                    completed_at=now(),
                )
            )
            run = session.scalar(
                select(WorkflowRun)
                .where(
                    WorkflowRun.background.is_(True),
                    WorkflowRun.attempt < MAX_ATTEMPTS,
                    or_(
                        and_(WorkflowRun.status == "queued", WorkflowRun.available_at <= now()),
                        and_(WorkflowRun.status == "running", WorkflowRun.expires_at <= now()),
                    ),
                )
                .order_by(WorkflowRun.started_at, WorkflowRun.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if run is None:
                return None
            story = session.get(StoryProject, run.story_id)
            if story is None or not story.owner_id:
                run.status = run.stage = "failed"
                run.error_code = "owner_missing"
                run.completed_at = now()
                return None
            run.attempt += 1
            run.status = "running"
            run.stage = "planning"
            run.lease_token = str(uuid4())
            run.expires_at = now() + timedelta(seconds=LEASE_SECONDS)
            run.error_code = None
            return Job(
                run.id,
                story.owner_id,
                run.lease_token,
                run.attempt,
                StoryRequest.model_validate(story.request),
            )

    @staticmethod
    def owned(job):
        return (
            WorkflowRun.id == job.run_id,
            WorkflowRun.status == "running",
            WorkflowRun.lease_token == job.token,
            WorkflowRun.expires_at > now(),
        )

    def heartbeat(self, job):
        with self.engine.begin() as connection:
            changed = connection.execute(
                update(WorkflowRun)
                .where(*self.owned(job))
                .values(expires_at=now() + timedelta(seconds=LEASE_SECONDS))
            )
            if changed.rowcount != 1:
                raise RunExpired()

    def progress(self, job, stage):
        with self.engine.begin() as connection:
            changed = connection.execute(
                update(WorkflowRun).where(*self.owned(job)).values(stage=stage)
            )
            if changed.rowcount != 1:
                raise RunExpired()

    def fail(self, job, code):
        retry = code in RETRYABLE and job.attempt < MAX_ATTEMPTS
        with self.engine.begin() as connection:
            connection.execute(
                update(WorkflowRun)
                .where(*self.owned(job))
                .values(
                    status="queued" if retry else "failed",
                    stage="retry_wait" if retry else "failed",
                    error_code=code,
                    lease_token=None,
                    completed_at=None if retry else now(),
                    available_at=now() + timedelta(seconds=15 * (2 ** (job.attempt - 1))),
                )
            )
