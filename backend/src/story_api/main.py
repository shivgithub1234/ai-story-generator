"""HTTP entry point; see the repository README for the development server command."""

from fastapi import FastAPI

from story_api.schemas import HealthResponse, StoryRequest, ValidationResponse

app = FastAPI(
    title="AI Story Generator & Evaluator",
    version="0.1.0",
    description=(
        "Stage 1: backend foundation and input validation. "
        "Generation, evaluation, and storage are planned for later stages."
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
