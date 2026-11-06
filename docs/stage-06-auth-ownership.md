# Stage 6 — Clerk authentication and private stories

The backend now requires a verified bearer token for story generation and saved-story operations. Clerk handles account creation, sign-in, password security, and session management. This project stores no passwords and issues no login tokens. The sign-in UI will be wired into the Next.js frontend next; live Clerk setup is required before using these protected endpoints outside tests.

## How identity becomes ownership

1. The frontend signs the user in through Clerk and obtains a short-lived session token.
2. It sends `Authorization: Bearer <token>` to FastAPI.
3. FastAPI verifies the RS256 signature using the configured JWKS endpoint, then checks issuer, audience, expiration, issued-at time, subject, and authorized party. A pending Clerk session is rejected. The token cannot choose its own verification URL or algorithm.
4. The verified `(issuer, subject)` pair resolves to an `app_users` row. Concurrent first requests cannot create duplicate accounts because the pair has a unique constraint.
5. A new story receives that user's local UUID as `owner_id`. API requests cannot submit or change the owner.

`GET /api/auth/me` returns the verified local user ID and provider identity. Email addresses are not used as ownership keys. Changing email does not transfer stories.

## Configure Clerk

Create or select your application in the [Clerk Dashboard](https://dashboard.clerk.com/). In its session-token customization, add the audience claim:

```json
{"aud": "story-api"}
```

Use your instance's exact issuer and JWKS URL, and configure the backend `.env`:

```dotenv
AUTH_ISSUER=https://YOUR_INSTANCE.clerk.accounts.dev
AUTH_AUDIENCE=story-api
AUTH_JWKS_URL=https://YOUR_INSTANCE.clerk.accounts.dev/.well-known/jwks.json
AUTH_AUTHORIZED_PARTIES=http://localhost:3000
```

Replace the placeholder with values from your Clerk instance. The issuer must match exactly; production Clerk domains may differ. Authorized parties are a comma-separated allowlist of exact frontend origins, not wildcards. Add your actual production frontend origin when deploying. Do not add origins you do not control. No Clerk secret key is needed for this public-key verification path.

From a Clerk-authenticated frontend, obtain the session token with its SDK's `getToken()` and send it in the Authorization header. `/docs` supports the **Authorize** button: supply a valid short-lived token obtained from your own signed-in frontend session, then call `/api/auth/me`. Do not send tokens in URL query parameters, commit them, paste them into chat, or save them in frontend localStorage.

Example request from an initialized Clerk frontend:

```typescript
const token = await getToken(); // from Clerk's useAuth()
const response = await fetch("http://127.0.0.1:8000/api/auth/me", {
  headers: { Authorization: `Bearer ${token}` },
});
```

For cross-origin browser calls, frontend/proxy and CORS integration will be added with the UI. The snippet shows header construction, not a complete standalone sign-in page. Until then, Swagger or a non-browser HTTP client can exercise the API using a valid token.

Restart the API after changing auth configuration; the verifier and public-key set are cached. Missing configuration returns 503, never an authentication bypass. Missing/invalid credentials return 401. Key-fetch outages return 503. Public keys are cached for five minutes and an unknown key ID prompts refresh for key rotation. Tokens are validated locally: provider logout or account disabling may not invalidate an already-issued token before its expiry. Use Clerk's short-lived session tokens and refresh through its SDK.

## Migrate the database

Install dependencies and run the existing initializer from the repository root:

```powershell
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.lock
.\.venv\Scripts\python.exe -m pip install --no-deps ./backend
$env:PYTHONPATH = (Resolve-Path backend/src).Path
.\.venv\Scripts\python.exe -m story_api.database
```

Schema version 2 adds `app_users` and indexed `story_projects.owner_id` with a foreign key. The migration is transactional and repeatable. It upgrades existing version-1 databases without deleting their stories, runs, drafts, or evaluations.

Existing stories keep a null owner and are inaccessible to every signed-in user. They are never assigned to the first person who logs in. For a legacy story whose rightful owner you have verified, first have that account call `/api/auth/me`, then run this local administrator command with its returned user ID:

```powershell
.\.venv\Scripts\python.exe -m story_api.assign_legacy --story-id STORY_UUID --user-id USER_UUID
```

This assigns exactly one ownerless story. It refuses missing users, missing stories, and already-owned stories. It is not an HTTP endpoint. Do not use it to transfer ownership of someone else's story.

## Protected operations

All saved-story lists, reads, edits, regeneration, and run history are filtered by the verified owner. Internal run completion, failure recording, and expiry recovery also stay within that owner's stories. Drafts and evaluations inherit access through the parent story/run; there are no unscoped public draft endpoints.

Another user's story ID produces the same 404 as an unknown ID. The backend never trusts `owner_id`, `user_id`, email, or an `X-User-ID` header as authentication. Manual edits still use version checking. The stateless `/api/stories/generate` endpoint also requires a verified token, including in demo mode; it does not require a local user row or database. `/health`, input validation, and API documentation remain public and do not reveal saved content or spend model credits.

This adds authentication and ownership controls, not a complete public-production platform. Per-user rate limits, account deletion workflows, operational monitoring, and the frontend are not implemented yet.

## Tests and Git checkpoint

Validation: all 105 tests passed with the PostgreSQL integration tests enabled. Ruff lint and formatting checks passed.

Tests use generated RSA keys, real signature checks, and an isolated PostgreSQL database. They cover incorrect signatures/algorithms, expiry, issuer/audience/authorized-party mismatch, public-key selection, unauthenticated routes, user isolation, ownership-injection attempts, stable local identity, legacy assignment, and a version-1 migration. Unit tests for the earlier workflow use an explicit test-only dependency override; there is no runtime development-auth bypass.

This stage is committed locally on `codex/stage-6-auth-ownership`. When ready:

```powershell
git push -u origin codex/stage-6-auth-ownership
```

The next stage is the Next.js frontend with Clerk sign-in and a personal story dashboard. Live Clerk sign-in has not been verified without your instance configuration and frontend session.

References: [Clerk token verification](https://clerk.com/docs/guides/sessions/manual-jwt-verification), [Clerk session tokens](https://clerk.com/docs/guides/sessions/session-tokens), [PyJWT verification options](https://pyjwt.readthedocs.io/en/latest/api.html).
