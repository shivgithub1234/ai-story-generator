# AI Story Generator & Evaluator

A portfolio project being built in working stages. The planned application turns a story premise into an outline, a scene-based script, and a rubric-based quality report, with at most one automatic revision per run.

**Current milestone: Stage 2 — Planner and Writer.** FastAPI runs a two-agent LangGraph workflow with Google Gemini, returning a structured outline and scene-based script. The default offline demo uses fixed sample data and requires no API key. Evaluation, feedback-based revision, persistence, and the frontend are not implemented yet.

## Run locally on Windows

Requires Python 3.12 and Git. Run these commands from the repository root in PowerShell:

```powershell
$env:PYTHONUTF8 = '1'
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.lock
.\.venv\Scripts\python.exe -m pip install --no-deps ./backend
.\.venv\Scripts\python.exe -m uvicorn story_api.main:app --app-dir backend/src --reload
```

Open http://127.0.0.1:8000/docs for the interactive API documentation, or http://127.0.0.1:8000/health for the health check. Stop the server with Ctrl+C. Calling the virtual environment's Python directly avoids PowerShell activation-policy issues.

Set `$env:PYTHONUTF8 = '1'` in each new PowerShell terminal before using this environment. This supports workspace paths containing non-English characters on Windows with Python 3.12.

On macOS/Linux, create the environment with `python3.12 -m venv .venv` and replace `.\.venv\Scripts\python.exe` with `.venv/bin/python` in the commands above.

## Try a story request

In `/docs`, expand `POST /api/story-requests/validate`, choose **Try it out**, paste this JSON, and choose **Execute**:

```json
{
  "premise": "A detective in Jaipur receives letters predicting crimes.",
  "genre": "mystery",
  "language": "English",
  "target_words": 1000,
  "tone": "Suspenseful"
}
```

A valid request returns HTTP 200 with normalized input. Invalid input returns HTTP 422 with field-specific details. This endpoint only validates; it does not call an AI model or persist data.

Submit the same JSON to **`POST /api/stories/generate`** to run the Planner → Writer graph. The response includes the outline, script, readable text, prompt version, timing, and token usage when available. By default, `is_demo` is true: the result is a fixed sample that ignores your preferences, not an AI-generated story.

For live Gemini generation, copy `.env.example` to `.env` once and set `STORY_PROVIDER=gemini`, `GEMINI_API_KEY`, and `GEMINI_MODEL` locally. Use a model available in your account that supports structured JSON. Restart the server after configuration changes. See the [Stage 2 walkthrough](docs/stage-02-planner-writer.md) for setup and response explanations. Never commit your `.env` file.

Initial supported genres: mystery, fantasy, science-fiction, drama, comedy, horror. Languages: English and Hindi. Premises must contain 10–2,000 characters after trimming, and target length must be an integer from 200–3,000 words. Target length will be approximate during generation.

## Verify

```powershell
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe -m ruff check backend
.\.venv\Scripts\python.exe -m ruff format --check backend
```

## Repository layout

```text
backend/
  pyproject.toml              Package metadata and dependency ranges
  requirements-dev.lock      Exact versions used for this milestone
  src/story_api/main.py      FastAPI application and HTTP routes
  src/story_api/schemas.py   Typed input and response contracts
  src/story_api/workflow.py  LangGraph Planner → Writer
  src/story_api/providers.py Gemini adapter and explicit offline demo
  src/story_api/prompts.py   Versioned agent instructions
  src/story_api/generation_models.py  Outline and script schemas
  tests/test_api.py          HTTP validation tests
  tests/test_generation.py   Workflow and provider failure tests
docs/
  stage-01-foundation.md     Explanation and GitHub checkpoint
  stage-02-planner-writer.md Generation workflow walkthrough
  roadmap.md                Planned milestones
```

## Architecture and planned extensions

Implemented: FastAPI → LangGraph Planner → Writer → response, with a Gemini provider adapter. Next: evaluator → at most one feedback-based rewrite. Later, a Next.js UI and PostgreSQL will provide editing and durable project history. An optional MCP interface will reuse the same application services.

The synchronous HTTP workflow is bounded by a 150-second deadline. Results are not saved. This development API has no authentication or public rate limiting; run it on localhost. Automated tests use fixtures/mocks and do not require paid model calls. Live Gemini output quality must be checked separately with your own configured account.

See [the roadmap](docs/roadmap.md) and [Stage 1 walkthrough](docs/stage-01-foundation.md). Audio/video generation and self-hosted model serving are outside the initial scope.

## Dependencies and secrets

The lock file records the tested development environment; `pyproject.toml` declares direct dependency ranges. After intentional dependency changes, regenerate the lock from a clean environment and rerun verification. Keep future credentials in an ignored `.env` file and publish only placeholder examples. Never commit API keys.
