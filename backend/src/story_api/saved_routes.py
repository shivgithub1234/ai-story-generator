"""Saved-story API; the original generation endpoint remains stateless."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from starlette.concurrency import run_in_threadpool

from story_api.auth import User, current_user
from story_api.database import get_engine
from story_api.schemas import StoryRequest
from story_api.storage import StoryStore

router = APIRouter(prefix="/api/stories", tags=["saved stories"])


def get_store(user: Annotated[User, Depends(current_user)]):
    return StoryStore(get_engine(), user.id)


Store = Annotated[StoryStore, Depends(get_store)]
PageSize = Annotated[int, Query(ge=1, le=50)]
Offset = Annotated[int, Query(ge=0)]


class StoryEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, strict=True)
    title: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
        | None
    ) = None
    edited_text: Annotated[str, StringConstraints(min_length=1, max_length=100000)] | None = None

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set - {"expected_version"}:
            raise ValueError("Provide title or edited_text")
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title cannot be null")
        return self


@router.post("", status_code=202)
async def save_new_story(request: StoryRequest, store: Store):
    story_id, _, _ = await run_in_threadpool(store.start, request, queued=True)
    return await run_in_threadpool(store.get, story_id)


@router.get("")
def list_stories(store: Store, limit: PageSize = 20, offset: Offset = 0):
    return store.list(limit, offset)


@router.get("/{story_id}")
def get_story(story_id: UUID, store: Store):
    return store.get(str(story_id))


@router.get("/{story_id}/runs")
def get_runs(story_id: UUID, store: Store, limit: PageSize = 20, offset: Offset = 0):
    return store.runs(str(story_id), limit, offset)


@router.post("/{story_id}/runs", status_code=202)
async def regenerate(story_id: UUID, store: Store):
    """Start a new run from the saved original request, not from manual edits."""
    await run_in_threadpool(store.start, story_id=str(story_id), queued=True)
    return await run_in_threadpool(store.get, str(story_id))


@router.patch("/{story_id}")
def edit_story(story_id: UUID, edit: StoryEdit, store: Store):
    changes = edit.model_dump(exclude_unset=True, exclude={"expected_version"})
    return store.edit(str(story_id), edit.expected_version, changes)
