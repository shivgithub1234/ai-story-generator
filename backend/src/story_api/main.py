"""HTTP entry point; see the repository README for the development server command."""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from story_api.auth import router as auth_router
from story_api.auth import verified_identity
from story_api.database import DatabaseConfigurationError, get_engine
from story_api.generation_models import GenerationResponse
from story_api.limits import UsageConfigurationError, UsageLimitExceeded
from story_api.preflight import validate_runtime
from story_api.providers import GenerationError, create_provider
from story_api.saved_routes import router as saved_router
from story_api.schemas import HealthResponse, StoryRequest, ValidationResponse
from story_api.storage import EditConflict, MissingStory, RunExpired
from story_api.workflow import generate_story


@asynccontextmanager
async def lifespan(app):
    validate_runtime()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="AI Story Generator & Evaluator",
    version="0.8.0",
    description=(
        "Stage 8: durable background jobs, progress, and private user-owned stories. "
        "Generation and saved-story operations require sign-in."
    ),
)


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Report whether the API process can respond; no external services are checked."""
    return HealthResponse()


@app.get("/ready", tags=["health"])
def ready():
    """Database/schema readiness only; this does not prove worker or Gemini health."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SET LOCAL statement_timeout = '3000ms'"))
            version = connection.execute(
                text("SELECT max(version) FROM story_schema_version")
            ).scalar()
            if version != 4:
                raise DatabaseConfigurationError("Schema migration required")
    except (SQLAlchemyError, DatabaseConfigurationError):
        return JSONResponse(
            status_code=503, content={"status": "not_ready"}, headers={"Cache-Control": "no-store"}
        )
    return JSONResponse(content={"status": "ready"}, headers={"Cache-Control": "no-store"})


@app.post("/api/story-requests/validate", response_model=ValidationResponse, tags=["stories"])
def validate_story_request(request: StoryRequest) -> ValidationResponse:
    """Validate and normalize input without generating or storing a story."""
    return ValidationResponse(request=request)


@app.post(
    "/api/stories/generate",
    response_model=GenerationResponse,
    tags=["stories"],
    dependencies=[Depends(verified_identity)],
)
async def create_story(request: StoryRequest) -> GenerationResponse:
    """Generate synchronously within this HTTP request; results are not persisted."""
    if os.getenv("STORY_ENABLE_UNMETERED_DEV_ENDPOINT", "false").lower() != "true":
        raise HTTPException(
            410,
            detail={
                "code": "use_saved_generation",
                "message": "Use POST /api/stories for generation with usage limits and progress.",
            },
        )
    provider = None
    try:
        provider = create_provider()
        async with asyncio.timeout(330):
            return await generate_story(request, provider)
    except GenerationError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.message}) from exc
    except TimeoutError as exc:
        raise HTTPException(
            504,
            detail={
                "code": "workflow_timeout",
                "message": "Story generation exceeded its time limit.",
            },
        ) from exc
    finally:
        if provider is not None:
            await provider.close()


async def storage_error_handler(request, exc):
    if isinstance(exc, MissingStory):
        status, code, message = 404, "story_not_found", "Story not found."
    elif isinstance(exc, EditConflict):
        status, code, message = 409, "edit_conflict", "Reload the story before saving your edits."
    elif isinstance(exc, RunExpired):
        status, code, message = 409, "run_expired", "This run expired; start a new run."
    else:
        status, code, message = (
            503,
            "database_unavailable",
            "Check database configuration and run the schema initializer.",
        )
    return JSONResponse(status_code=status, content={"detail": {"code": code, "message": message}})


@app.exception_handler(UsageLimitExceeded)
async def usage_limit_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content=jsonable_encoder(
            {
                "detail": {
                    "code": exc.code,
                    "message": exc.message,
                    "usage": exc.usage,
                }
            }
        ),
        headers={"Cache-Control": "private, no-store"},
    )


@app.exception_handler(UsageConfigurationError)
async def usage_config_handler(request, exc):
    return JSONResponse(
        status_code=503,
        content={
            "detail": {
                "code": "usage_configuration_error",
                "message": "Usage limits are not configured correctly.",
            }
        },
    )


for exception in (
    DatabaseConfigurationError,
    SQLAlchemyError,
    MissingStory,
    EditConflict,
    RunExpired,
):
    app.add_exception_handler(exception, storage_error_handler)

# Register after /generate so it cannot be interpreted as a story UUID.
app.include_router(saved_router)
app.include_router(auth_router)
