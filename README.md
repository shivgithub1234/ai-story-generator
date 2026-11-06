# AI Story Generator & Evaluator

A portfolio project being built in working stages. The planned application turns a story premise into an outline, a scene-based script, and a rubric-based quality report, with at most one automatic revision per run.

**Current milestone: Stage 6 — Clerk authentication and story ownership.** FastAPI runs a LangGraph Planner → Writer → Evaluator workflow with Google Gemini, followed by at most one rewrite and final evaluation when needed. Saved-story endpoints retain projects, runs, drafts, evaluations, and manual edits in PostgreSQL. Saved stories are private to their verified owners. Demo mode uses fixed sample stories and scores and needs no Gemini key, but still requires sign-in. The frontend is not implemented yet.

## Authentication setup

Configure Clerk and apply schema version 2 using the [Stage 6 walkthrough](docs/stage-06-auth-ownership.md). Generation and saved-story endpoints now require a valid bearer token, including demo mode. Use `/api/auth/me` to confirm your local account ID. Existing ownerless stories remain inaccessible until explicitly assigned by an administrator. No live Clerk application has been configured automatically.

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

Submit the same JSON to **`POST /api/stories/generate`** with a valid Authorization bearer token to run the Planner → Writer → Evaluator graph. The response includes the outline, script, readable text, evaluation, prompt version, timing, and token usage when available. By default, `is_demo` is true: the story and scores are fixed samples that ignore your preferences, not AI-generated results.

The judge scores coherence, character consistency, repetition avoidance, language quality, and instruction adherence from 1–10, with scene evidence and revision suggestions. Python computes the average and flags an average below 7.0 or any individual dimension below 4 with `needs_revision`. This triggers one feedback-based rewrite and a final evaluation. The workflow then stops even if quality remains below the rule. See the [Stage 4 walkthrough](docs/stage-04-feedback-revision.md).

`initial_script` and `initial_evaluation` preserve the original output; `script`, `evaluation`, and `final_text` represent the final output. `revision_count` is 0 or 1, and `stop_reason` distinguishes `quality_passed` from `revision_limit_reached`. A rewrite is not guaranteed to improve the score. Demo mode intentionally ends with the latter result using fixed scores.

For live Gemini generation, copy `.env.example` to `.env` once and set `STORY_PROVIDER=gemini`, `GEMINI_API_KEY`, and `GEMINI_MODEL` locally. Use a model available in your account that supports structured JSON. Restart the server after configuration changes. See the [Stage 2 walkthrough](docs/stage-02-planner-writer.md) for setup and response explanations. Never commit your `.env` file.

To save results, configure `DATABASE_URL` and initialize PostgreSQL using the [Stage 5 setup guide](docs/stage-05-persistence.md). Submit the same request to `POST /api/stories`, then use `GET /api/stories/{id}` to reopen it and `GET /api/stories/{id}/runs` to inspect history. The existing `/generate` endpoint remains stateless and works without a database, but requires a verified token. `PATCH /api/stories/{id}` saves separate manual edits using `expected_version` to prevent lost updates.

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
  src/story_api/workflow.py  LangGraph Planner → Writer → Evaluator
  src/story_api/evaluation.py  Aggregate score and revision recommendation
  src/story_api/auth.py      Clerk bearer-token verification and local identity
  src/story_api/assign_legacy.py  Explicit admin assignment for ownerless stories
  src/story_api/database.py  Engine configuration and versioned schema initialization
  src/story_api/storage.py   PostgreSQL models and transactional persistence
  src/story_api/saved_routes.py Saved project and run endpoints
  src/story_api/providers.py Gemini adapter and explicit offline demo
  src/story_api/prompts.py   Versioned agent instructions
  src/story_api/generation_models.py  Outline and script schemas
  tests/test_api.py          HTTP validation tests
  tests/test_generation.py   Workflow and provider failure tests
  tests/test_evaluation.py   Rubric validation and threshold tests
  tests/test_revision.py     Conditional rewrite and limit tests
  tests/test_auth.py         Signed JWT and protected-route tests
  tests/test_ownership.py    Cross-user access and migration tests
  tests/test_storage.py      Real PostgreSQL integration tests (opt-in)
docs/
  stage-01-foundation.md     Explanation and GitHub checkpoint
  stage-02-planner-writer.md Generation workflow walkthrough
  stage-03-evaluator.md      Judge and scoring walkthrough
  stage-04-feedback-revision.md  Bounded rewrite walkthrough
  stage-05-persistence.md    Database setup and saved-story walkthrough
  stage-06-auth-ownership.md Clerk setup, ownership, and legacy migration
  evaluation-cases.json      Repeatable manual review prompts
  roadmap.md                Planned milestones
```

## Architecture and planned extensions

Implemented: FastAPI → LangGraph Planner → Writer → Evaluator → optional single rewrite → final evaluation, with a Gemini provider adapter and PostgreSQL persistence. Next, a Next.js UI will provide Clerk sign-in, a personal dashboard, editing, and review. An optional MCP interface will reuse the same application services.

The synchronous HTTP workflow is bounded by a 330-second deadline and makes three model calls, or five when revision is needed. Saved-story endpoints persist completed results; `/generate` does not. This API verifies Clerk tokens and enforces ownership, but public rate limiting is not implemented; keep development on localhost. Model tests use fixtures/mocks and do not require paid calls. PostgreSQL tests require `STORY_TEST_DATABASE_URL` and otherwise skip explicitly. Live Gemini output quality must be checked separately with your own configured account. Judge scores are subjective estimates; cited scene numbers are validated but the accuracy of evidence is not automatically verified.

See [the roadmap](docs/roadmap.md) and [Stage 1 walkthrough](docs/stage-01-foundation.md). Audio/video generation and self-hosted model serving are outside the initial scope.

## Dependencies and secrets

The lock file records the tested development environment; `pyproject.toml` declares direct dependency ranges. After intentional dependency changes, regenerate the lock from a clean environment and rerun verification. Keep future credentials in an ignored `.env` file and publish only placeholder examples. Never commit API keys.
