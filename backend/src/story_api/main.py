"""HTTP entry point; see the repository README for the development server command."""

import asyncio

from fastapi import FastAPI, HTTPException

from story_api.generation_models import GenerationResponse
from story_api.providers import GenerationError, create_provider
from story_api.schemas import HealthResponse, StoryRequest, ValidationResponse
from story_api.workflow import generate_story

app = FastAPI(
    title="AI Story Generator & Evaluator",
    version="0.3.0",
    description=(
        "Stage 3: Planner, Writer, and rubric-based judge with Gemini or offline demo mode. "
        "Automatic revision and storage are planned for later stages."
    ),
)


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Report whether the API process can respond; no external services are checked."""
    return HealthResponse()


@app.post("/api/story-requests/validate", response_model=ValidationResponse, tags=["stories"])
def validate_story_request(request: StoryRequest) -> ValidationResponse:
    """Validate and normalize input without generating or storing a story."""
    return ValidationResponse(request=request)


@app.post("/api/stories/generate", response_model=GenerationResponse, tags=["stories"])
async def create_story(request: StoryRequest) -> GenerationResponse:
    """Generate synchronously within this HTTP request; results are not persisted."""
    provider = None
    try:
        provider = create_provider()
        async with asyncio.timeout(210):
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
