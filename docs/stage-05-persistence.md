# Stage 5 — PostgreSQL persistence

Stages 1–4 produced results only in the HTTP response. Stage 5 adds saved projects, run history, original and revised drafts, evaluation reports, and manual edits. The generation workflow and one-rewrite rule are unchanged.

## The four tables

| Table | Stores |
| --- | --- |
| `story_projects` | Original request, display title, creation time, separately saved manual text, edit version |
| `workflow_runs` | Run status, start/end times, expiry, safe error code, complete successful response snapshot |
| `story_drafts` | Outline and structured script for each generated revision (0 and optionally 1) |
| `evaluations` | Rubric report linked to exactly one draft |

Structured fields use PostgreSQL JSONB. IDs, status, versions, relationships, and timestamps use ordinary columns. Foreign keys and unique constraints prevent duplicate draft revision numbers and multiple evaluation records for the same draft. The complete run response is also retained as a JSONB snapshot so historical API results remain reproducible; this deliberately duplicates some normalized draft/evaluation data.

## Set up your local database

PostgreSQL 18 is installed on this machine. Use your own administrator login to create a dedicated app user and database. From PowerShell:

```powershell
& 'C:/Program Files/PostgreSQL/18/bin/psql.exe' -h 127.0.0.1 -U postgres -d postgres
```

Inside psql, run these once (choose different names if they already exist):

```sql
CREATE USER story_app;
\password story_app
CREATE DATABASE ai_story_generator OWNER story_app;
\q
```

The password command prompts privately. In your local `.env` file set:

```dotenv
STORY_PROVIDER=demo
DATABASE_URL=postgresql+psycopg://story_app:YOUR_PASSWORD@127.0.0.1:5432/ai_story_generator
```

Percent-encode reserved URL characters in the password. Do not commit `.env`. Use a dedicated database rather than an unrelated project's database. To generate real stories, change the provider to Gemini and configure the key/model as in Stage 2.

From the repository root, install the updated dependencies and initialize the schema:

```powershell
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.lock
.\.venv\Scripts\python.exe -m pip install --no-deps ./backend
$env:PYTHONPATH = (Resolve-Path backend/src).Path
.\.venv\Scripts\python.exe -m story_api.database
.\.venv\Scripts\python.exe -m uvicorn story_api.main:app --app-dir backend/src --reload
```

The initializer applies schema version 1 in a transaction, using a PostgreSQL advisory lock to serialize concurrent initializers. Repeating it is safe. It does not silently evolve existing columns: future schema changes require new explicit migrations. Application startup does not create tables automatically. Restart the API when changing DATABASE_URL because its engine configuration is cached.

## Endpoints

| Endpoint | Behavior |
| --- | --- |
| `POST /api/stories/generate` | Existing stateless generation; does not require PostgreSQL |
| `POST /api/stories` | Save a project, execute its first run, and return saved details (201) |
| `GET /api/stories` | List project summaries with `limit` (1–50) and `offset` |
| `GET /api/stories/{id}` | Retrieve request, manual edits, version, and latest run/output |
| `GET /api/stories/{id}/runs` | Paginated run history, including successful outputs and failures |
| `POST /api/stories/{id}/runs` | Generate a new run from the saved original request |
| `PATCH /api/stories/{id}` | Change title or save manual text with optimistic version checking |

Try the README request JSON with `POST /api/stories` in `/docs`. Copy the returned story `id`, restart the API, and retrieve it with GET. The response snapshot's `run_id` matches its persisted run row. Every new run leaves previous runs intact.

A new run uses the saved original request, not `edited_text`. This is regeneration, not a user-directed edit of the current story. Editing metadata does not change the saved original request or generated snapshots.

## Save manual edits without overwriting another save

Read the project's `version`, then send:

```json
{
  "expected_version": 1,
  "title": "My edited story",
  "edited_text": "The text I edited myself..."
}
```

Success increments the version. A stale version returns 409, so the caller must reload and reconcile changes. Omit `edited_text` to preserve it; send `edited_text: null` to clear it. The generated drafts and their evaluations are immutable through these endpoints. `edits_evaluated: false` makes clear that manual text has no AI assessment attached.

## Transaction and failure behavior

The app commits a `running` row before calling the model, then releases the database connection. Model generation does not hold a database transaction open. Completion saves both drafts, both evaluations when a revision occurred, and the successful response in one transaction. Any failure rolls that transaction back; partial completed results are not exposed.

Handled model failures mark the run `failed`, storing only a safe error code. The error response includes story/run IDs so history can be inspected. If a process crashes, its running record has a ten-minute expiry. Reading a story or its run history marks expired running records failed with `run_interrupted`. This recovery is lazy, not a background worker. It does not resume generation or recover intermediate model outputs. A database outage can delay recording failure until a later read performs expiry recovery.

Database errors return a generic 503 without exposing connection credentials. Unknown IDs return 404. This is a local single-user API: authorization and durable background execution are still future work.

## Verification

The PostgreSQL integration tests use `STORY_TEST_DATABASE_URL`. Each test creates and removes only its own randomly named schema; it never resets existing tables. Use a dedicated test database whose user can create schemas:

```powershell
$env:STORY_TEST_DATABASE_URL = $env:DATABASE_URL
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

That example assumes DATABASE_URL is set in your shell, not only in `.env`. Without STORY_TEST_DATABASE_URL, database tests are explicitly skipped; the rest of the suite still runs. Tests cover saving/reopening, normalized draft/evaluation rows, new-run history, stale edits, failed model calls, interrupted runs, schema initialization, and atomic rollback.

## Git checkpoint

Checkpoint verification: 77 tests passed, including six real PostgreSQL integration tests using an isolated PostgreSQL 18 cluster. A separate API smoke check saved a demo story, restarted PostgreSQL, and reopened the full result from a fresh Python process. Ruff lint/format checks and `pip check` passed. The isolated test server was stopped afterward; your normal PostgreSQL service and existing databases were not changed. Configure your own DATABASE_URL using the setup above for regular use. Live Gemini generation remains unverified.

Stage 4 is published on `codex/stage-4-feedback-revision`. Stage 5 is developed locally on `codex/stage-5-persistence`:

```powershell
git push -u origin codex/stage-5-persistence
```

Compare against Stage 4 for a focused review, or use `main` after earlier stages are merged. Next: the Next.js interface for creating, reviewing, editing, and reopening stories.
