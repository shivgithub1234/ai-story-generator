"""Short transactions: never hold a database transaction during model generation."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from story_api.database import Base
from story_api.generation_models import GenerationResponse
from story_api.limits import UsageLimitExceeded, get_limits
from story_api.schemas import StoryRequest


def now():
    return datetime.now(UTC)


class StoryProject(Base):
    __tablename__ = "story_projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("app_users.id"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(300))
    request: Mapped[dict] = mapped_column(JSONB)
    edited_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AppUser(Base):
    __tablename__ = "app_users"
    __table_args__ = (UniqueConstraint("issuer", "subject"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    issuer: Mapped[str] = mapped_column(String(500))
    subject: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    story_id: Mapped[str] = mapped_column(ForeignKey("story_projects.id"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    background: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    stage: Mapped[str] = mapped_column(String(30), default="queued", server_default="queued")
    attempt: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StoryDraft(Base):
    __tablename__ = "story_drafts"
    __table_args__ = (UniqueConstraint("run_id", "revision_number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id"), index=True)
    revision_number: Mapped[int] = mapped_column(Integer)
    outline: Mapped[dict] = mapped_column(JSONB)
    script: Mapped[dict] = mapped_column(JSONB)


class Evaluation(Base):
    __tablename__ = "evaluations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("story_drafts.id"), unique=True)
    report: Mapped[dict] = mapped_column(JSONB)


class MissingStory(Exception):
    pass


class EditConflict(Exception):
    pass


class RunExpired(Exception):
    pass


class StoryStore:
    def __init__(self, engine, owner_id: str):
        if not owner_id:
            raise ValueError("A verified owner is required")
        self.engine = engine
        self.owner_id = owner_id

    def _owned_story(self, session, story_id):
        story = session.scalar(
            select(StoryProject).where(
                StoryProject.id == story_id,
                StoryProject.owner_id == self.owner_id,
            )
        )
        if story is None:
            raise MissingStory()
        return story

    def _owned_ids(self):
        return select(StoryProject.id).where(StoryProject.owner_id == self.owner_id)

    def start(
        self, request: StoryRequest | None = None, story_id: str | None = None, *, queued=False
    ):
        with Session(self.engine) as session, session.begin():
            # All admissions for one account share this lock, including different stories.
            owner = session.scalar(
                select(AppUser).where(AppUser.id == self.owner_id).with_for_update()
            )
            if owner is None:
                raise MissingStory()
            if story_id is not None:
                story = self._owned_story(session, story_id)
                request = StoryRequest.model_validate(story.request)
                if queued:
                    active = session.scalar(
                        select(WorkflowRun).where(
                            WorkflowRun.story_id == story_id,
                            WorkflowRun.status.in_(["queued", "running"]),
                            WorkflowRun.background.is_(True),
                        )
                    )
                    if active:
                        return story_id, active.id, request
            if queued:
                usage = self._usage(session)
                if usage["remaining"] == 0:
                    raise UsageLimitExceeded(
                        "daily_usage_limit",
                        "Your generation allowance is used up. "
                        "Wait for a request to leave the rolling 24-hour window.",
                        usage,
                    )
                if usage["active_jobs"] >= usage["active_limit"]:
                    raise UsageLimitExceeded(
                        "active_job_limit",
                        "You already have the maximum number of active jobs. "
                        "Wait for one to finish before starting another.",
                        usage,
                    )
            if story_id is None:
                story_id = str(uuid4())
                session.add(
                    StoryProject(
                        id=story_id,
                        owner_id=self.owner_id,
                        title=request.premise[:300],
                        request=request.model_dump(),
                    )
                )
                session.flush()
            run_id = str(uuid4())
            session.add(
                WorkflowRun(
                    id=run_id,
                    story_id=story_id,
                    status="queued" if queued else "running",
                    started_at=usage["checked_at"] if queued else now(),
                    background=queued,
                    available_at=now() if queued else None,
                    expires_at=now() + timedelta(minutes=10),
                )
            )
        return story_id, run_id, request

    def _usage(self, session):
        limits = get_limits()
        # Clock time is read after acquiring the account lock, not at transaction start.
        checked_at = session.scalar(select(func.clock_timestamp()))
        recent = (
            WorkflowRun.story_id.in_(self._owned_ids()),
            WorkflowRun.started_at > checked_at - timedelta(hours=24),
        )
        used = session.scalar(select(func.count()).select_from(WorkflowRun).where(*recent))
        active = session.scalar(
            select(func.count())
            .select_from(WorkflowRun)
            .where(
                WorkflowRun.story_id.in_(self._owned_ids()),
                WorkflowRun.background.is_(True),
                WorkflowRun.status.in_(["queued", "running"]),
            )
        )
        release = session.scalar(
            select(WorkflowRun.started_at)
            .where(*recent)
            .order_by(WorkflowRun.started_at)
            .offset(max(0, used - limits.requests_per_24h))
            .limit(1)
        )
        return {
            "limit": limits.requests_per_24h,
            "used": used,
            "remaining": max(0, limits.requests_per_24h - used),
            "active_jobs": active,
            "active_limit": limits.active_jobs,
            "next_credit_at": release + timedelta(hours=24) if release else None,
            "checked_at": checked_at,
        }

    def usage(self):
        with Session(self.engine) as session:
            return self._usage(session)

    def finish(self, run_id: str, result: GenerationResponse, *, lease_token=None):
        with Session(self.engine) as session, session.begin():
            run = session.scalar(
                select(WorkflowRun)
                .where(
                    WorkflowRun.id == run_id,
                    WorkflowRun.story_id.in_(self._owned_ids()),
                )
                .with_for_update()
            )
            if (
                run is None
                or run.status != "running"
                or run.expires_at <= now()
                or (run.background and run.lease_token != lease_token)
            ):
                raise RunExpired()
            output = result.model_copy(update={"run_id": run_id}).model_dump(mode="json")
            drafts = [(result.initial_script, result.initial_evaluation)]
            if result.revision_count:
                drafts.append((result.script, result.evaluation))
            for number, (script, report) in enumerate(drafts):
                draft_id = str(uuid4())
                session.add(
                    StoryDraft(
                        id=draft_id,
                        run_id=run_id,
                        revision_number=number,
                        outline=result.outline.model_dump(),
                        script=script.model_dump(),
                    )
                )
                session.flush()
                session.add(
                    Evaluation(id=str(uuid4()), draft_id=draft_id, report=report.model_dump())
                )
            run.status = "completed"
            run.stage = "completed"
            run.lease_token = None
            run.completed_at = now()
            run.output = output

    def fail(self, run_id: str, code: str):
        with Session(self.engine) as session, session.begin():
            session.execute(
                update(WorkflowRun)
                .where(
                    WorkflowRun.id == run_id,
                    WorkflowRun.story_id.in_(self._owned_ids()),
                    WorkflowRun.status == "running",
                )
                .values(status="failed", error_code=code, completed_at=now())
            )

    def _expire(self, session):
        session.execute(
            update(WorkflowRun)
            .where(
                WorkflowRun.status == "running",
                WorkflowRun.background.is_(False),
                WorkflowRun.expires_at < now(),
                WorkflowRun.story_id.in_(self._owned_ids()),
            )
            .values(status="failed", error_code="run_interrupted", completed_at=now())
        )

    @staticmethod
    def _run(run, *, include_output=True):
        data = {
            "id": run.id,
            "status": run.status,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "error_code": run.error_code,
            "stage": run.stage,
            "attempt": run.attempt,
            "available_at": run.available_at,
        }
        if include_output:
            data["output"] = run.output
        return data

    def get(self, story_id: str):
        with Session(self.engine) as session, session.begin():
            self._expire(session)
            story = self._owned_story(session, story_id)
            latest = session.scalar(
                select(WorkflowRun)
                .where(
                    WorkflowRun.story_id == story_id,
                )
                .order_by(WorkflowRun.started_at.desc(), WorkflowRun.id.desc())
                .limit(1)
            )
            return {
                "id": story.id,
                "owner_id": story.owner_id,
                "title": story.title,
                "request": story.request,
                "created_at": story.created_at,
                "version": story.version,
                "edited_text": story.edited_text,
                "edits_evaluated": False,
                "latest_run": self._run(latest) if latest else None,
            }

    def runs(self, story_id: str, limit: int, offset: int):
        with Session(self.engine) as session, session.begin():
            self._expire(session)
            self._owned_story(session, story_id)
            runs = session.scalars(
                select(WorkflowRun)
                .where(WorkflowRun.story_id == story_id)
                .order_by(WorkflowRun.started_at.desc(), WorkflowRun.id.desc())
                .limit(limit)
                .offset(offset)
            )
            return [self._run(run) for run in runs]

    def list(self, limit: int, offset: int):
        with Session(self.engine) as session:
            stories = session.scalars(
                select(StoryProject)
                .where(StoryProject.owner_id == self.owner_id)
                .order_by(StoryProject.created_at.desc(), StoryProject.id.desc())
                .limit(limit)
                .offset(offset)
            )
            return [
                {"id": s.id, "title": s.title, "version": s.version, "created_at": s.created_at}
                for s in stories
            ]

    def edit(self, story_id: str, expected_version: int, changes: dict):
        with Session(self.engine) as session, session.begin():
            self._owned_story(session, story_id)
            updated = session.execute(
                update(StoryProject)
                .where(
                    StoryProject.id == story_id,
                    StoryProject.owner_id == self.owner_id,
                    StoryProject.version == expected_version,
                )
                .values(**changes, version=expected_version + 1)
            )
            if updated.rowcount != 1:
                raise EditConflict()
        return self.get(story_id)
