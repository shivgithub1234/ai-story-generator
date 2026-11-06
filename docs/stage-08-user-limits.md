# Stage 8b — Per-user usage limits

Background workers let users leave the page while stories generate. Admission limits control how much work each account can add to that queue.

## Policy

The default allowance is **10 generation requests in a rolling 24-hour window**, with at most **2 active jobs** per account. Queued jobs, running jobs, and jobs waiting for an automatic retry are active. The counters belong to the verified local user ID, not an IP address, browser, or user-provided owner field.

One new story or regeneration consumes one request when it is accepted. Automatic worker retries and the optional quality rewrite do not consume another request. Failed requests still count because a failure can happen after model calls have been billed. Existing runs from the last 24 hours count too. Repeated regeneration submissions for a story that already has an active job return that existing job without consuming another request.

This is a rolling window, not a midnight reset. A request accepted at 3 pm becomes eligible to leave the window at 3 pm the following day. The UI shows the next available time in the browser's local timezone when the allowance is exhausted.

## How enforcement works

1. FastAPI verifies the Clerk token and resolves the account.
2. The enqueue transaction locks that account's `app_users` row.
3. It checks story ownership, reuses any existing active run, then reads the account's usage using PostgreSQL's clock.
4. If either limit is reached, it returns HTTP 429 with `daily_usage_limit` or `active_job_limit`. No new project or run is committed.
5. Otherwise the same transaction saves the job and releases the lock.

Locking the account makes simultaneous submissions from different tabs or API processes wait for each other. Checking the count without this lock would allow both requests to see the same remaining slot. Different users have separate locks and allowances. Workers do not take this admission lock while making Gemini calls.

`GET /api/stories/usage` returns the caller's limit, used/remaining requests, active jobs, active limit, check time, and next credit time. It requires authentication and uses private, uncached responses. The dashboard refreshes this summary every 15 seconds and on job/status changes. The summary is informative; the backend always makes the final admission decision. Reading, downloading, and editing existing stories remain available at the limit.

## Configuration

Add these server-side settings to the ignored root `.env` if you want different values:

```dotenv
STORY_REQUESTS_PER_24H=10
STORY_MAX_ACTIVE_JOBS=2
STORY_ENABLE_UNMETERED_DEV_ENDPOINT=false
```

Restart the API after changing environment configuration. Positive values are required: 1–10,000 requests per day and 1–100 active jobs. Invalid configuration fails closed with HTTP 503. No schema migration or new dependency is required; counters are calculated from persisted runs and survive restarts.

The old synchronous `POST /api/stories/generate` endpoint is **disabled by default** and returns 410 after authentication. Use `POST /api/stories` instead. The explicit `STORY_ENABLE_UNMETERED_DEV_ENDPOINT=true` switch retains it for local model experiments only; that endpoint is unmetered, so never enable the switch on a shared or public deployment. Automated model tests enable it only inside their test fixture.

## What this does not claim

These are request and active-job limits, not exact token or currency budgets. Each request can make several model calls and retry up to three times. This does not provide per-IP abuse prevention, account-creation protection, global queue capacity, or round-robin fairness. Those are separate deployment controls. Multiple worker processes still pick the oldest eligible jobs.

## Verification

The backend suite passed 126 tests using isolated PostgreSQL. Six frontend tests, TypeScript checking, the production build, and Ruff checks passed. The signed-in dashboard was also checked against Neon: it displayed 4 of 10 requests remaining and 0 of 2 active jobs for the existing account, including earlier run history.

PostgreSQL tests cover simultaneous submissions competing for the last allowance/active slot, independent users, persistence across reconnection, failed requests, rolling-window expiry, duplicate regeneration, and rejected submissions leaving no empty project. Configuration and legacy-endpoint tests verify fail-closed behavior. Existing ownership and worker tests remain applicable.

To try it without model costs, use demo mode on a separate test database, stop its worker, set the active-job limit to 1, submit once, and submit a second distinct story. The first should remain queued and the second should receive 429. Existing queued runs are not cancelled when a limit is lowered.

## Administrative allowance reset (schema 4)

`AppUser.usage_reset_at` lets an administrator reset one account's rolling usage without deleting stories, runs, or their timestamps. The usage window starts at the later of this timestamp and 24 hours ago. Active jobs still count, other accounts are unaffected, and later requests consume the normal allowance. `StoryStore.reset_usage()` takes the same account lock as admission, so a concurrent reset and request serialize. It is intentionally not exposed as a public API endpoint. Apply the additive schema-4 migration before deploying this code.
