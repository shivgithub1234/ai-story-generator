# AI Story Generator & Evaluator

A portfolio project being built in working stages. The planned application turns a story premise into an outline, a scene-based script, and a rubric-based quality report, with at most one automatic revision per run.

**Current milestone: Stage 1 — backend foundation.** The API runs locally and validates story inputs. It does not generate or save stories yet. No API key or database is required for this milestone.

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
  tests/test_api.py          HTTP validation tests
docs/
  stage-01-foundation.md     Explanation and GitHub checkpoint
  roadmap.md                Planned milestones
```

## Planned architecture

Next.js UI → FastAPI → LangGraph planner → writer → evaluator → optional revision. PostgreSQL will store projects, drafts, evaluations, and run history. A hosted LLM will sit behind a provider adapter. An optional MCP interface will reuse the same application services.

See [the roadmap](docs/roadmap.md) and [Stage 1 walkthrough](docs/stage-01-foundation.md). Audio/video generation and self-hosted model serving are outside the initial scope.

## Dependencies and secrets

The lock file records the tested development environment; `pyproject.toml` declares direct dependency ranges. After intentional dependency changes, regenerate the lock from a clean environment and rerun verification. Keep future credentials in an ignored `.env` file and publish only placeholder examples. Never commit API keys.
