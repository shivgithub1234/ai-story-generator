# Stage 7 — Story Studio frontend

Stage 8 changes saved generation to queued jobs and adds a required worker process. For the current startup and API behavior, see [Stage 8](stage-08-background-jobs.md). The notes below describe the original Stage 7 checkpoint.

This stage gives the existing FastAPI application a Next.js interface. The frontend is developed locally on `codex/stage-7-frontend`, based on Stage 6. Stage 6 is already pushed; this stage is a separate, reviewable checkpoint.

## What you can do

- Sign in or create an account with the existing Clerk application; sign out through the account avatar.
- Create a story from a premise, genre, language, target length, and optional tone.
- Browse a paginated personal library and reopen saved stories.
- Read scenes and dialogue, inspect the outline, and review all five evaluator dimensions with evidence.
- Compare the initial draft/evaluation after an automatic revision. The backend still permits at most one rewrite per run.
- Generate another run from the original brief and inspect prior runs.
- Save separate manual edits with optimistic version checking, and download plain text.

The interface distinguishes demo content, failed/running runs, revised drafts, and unevaluated manual edits. A failed model call can still leave a saved project; refresh the library rather than submitting repeatedly. Reloading during generation does not provide durable workflow resumption.

## How sign-in and private data work

The browser uses the official `@clerk/react` SDK inside a client-rendered Next.js page. It needs only the publishable key. We deliberately use the browser SDK because FastAPI already handles server authentication; this is not a Next.js server-auth implementation and does not use `auth()`, `currentUser()`, or Clerk middleware. No Clerk secret key is required for this architecture.

1. Clerk signs in the user and provides a short-lived token through `getToken()`.
2. Browser requests go to the same-origin `/api/backend/...` route with that bearer token.
3. The route accepts only the known story/auth paths and methods, forwards to the server-configured FastAPI origin, and does not forward cookies or follow redirects.
4. FastAPI checks the token signature and claims, resolves the user, and filters database queries by owner.
5. Private responses use `Cache-Control: private, no-store`. Switching Clerk users or sessions remounts the workspace, clearing its in-memory story state. Application code never puts tokens or stories into localStorage.

The browser's sign-in gate is a presentation feature, not the security boundary. Direct API requests still require verified tokens. Requests cannot choose an upstream host or supply a story owner. Both APIs must be hardened with rate limiting before public exposure.

## Local setup

Use Node.js 22 and Python 3.12. From the repository root, start the backend in one terminal:

```powershell
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m uvicorn story_api.main:app --app-dir backend/src --host 127.0.0.1 --port 8000
```

The root `.env` contains `DATABASE_URL`, Gemini settings, and the Stage 6 `AUTH_*` settings. Keep `AUTH_AUTHORIZED_PARTIES=http://localhost:3000` and the Clerk session-token audience `story-api`. Initialize the database with schema version 2 before opening the library.

In a second terminal:

```powershell
cd frontend
npm ci
Copy-Item .env.example .env.local # first setup only; do not overwrite an existing configured file
```

Edit `frontend/.env.local`:

```dotenv
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=your_clerk_publishable_key
STORY_API_URL=http://127.0.0.1:8000
```

Then run `npm run dev` and open **http://localhost:3000**. Use that exact origin (not `127.0.0.1:3000`) so Clerk's `azp` claim matches the backend allowlist. If port 3000 is occupied, stop the conflicting server before starting rather than using an unexpected port.

Only the publishable key is sent to the browser. Never put the Gemini key, database URL, or Clerk secret key in a `NEXT_PUBLIC_*` variable. Existing local secrets are Git-ignored and are not part of this commit.

Clerk enforces a minimum password length of 8 characters and can reject known breached passwords. These provider rules cannot be changed by adding a frontend `minLength` attribute. Google sign-in is also available when enabled in your Clerk application.

## File map

| File | Responsibility |
| --- | --- |
| `frontend/src/components/studio.tsx` | Clerk provider, session gate, brief form, library |
| `frontend/src/components/story-reader.tsx` | Drafts, feedback, outlines, editing, history |
| `frontend/src/lib/api.ts` | Bearer requests and actionable error messages |
| `frontend/src/lib/proxy.ts` | Restricted, uncached FastAPI forwarding |
| `frontend/src/app/api/backend/[...path]/route.ts` | Next.js route handler |
| `frontend/src/lib/types.ts` | Types matching backend response contracts |
| `frontend/src/app/globals.css` | Responsive workspace and reader styles |

## Verify

```powershell
cd frontend
npm run typecheck
npm test
npm run build
```

Proxy tests cover path/method restrictions, missing credentials, cross-origin mutations, forwarding only explicit bearer credentials, no private-response caching, and useful error messages. Backend Stage 6 tests cover cryptographic verification and cross-user isolation.

For a live smoke test: sign in, create a short story, inspect feedback, save an edit, reload it, open the library and run history, then sign out. Use a second Clerk account to check that its library excludes the first account's stories. Do not treat mocked tokens or a successful build as proof of live sign-in.

## Verification checkpoint

TypeScript checking, the four proxy tests, and the Next.js production build passed. Live HTTP checks returned 401 for missing/invalid bearer credentials and 404 for an unsupported path. The backend follow-up suite passed 97 tests, with 11 database integration tests skipped in this run; Stage 6 previously exercised isolation using a disposable PostgreSQL database.

After restoring network connectivity to Neon, the real Clerk account generated "The Fallen Orb" through Gemini, received an average evaluation of 9.2/10, and saved the result. Browser checks confirmed all five feedback dimensions, saving the title and a separate manuscript copy, reopening that copy from the personal library, and history showing the completed run alongside earlier failed attempts. A second-account browser isolation check has not been performed.

Live testing used `GEMINI_MODEL=gemini-3.1-flash-lite` in the ignored local environment. It also exposed a writer-schema compatibility issue: the nested dialogue array's `maxItems=60` caused Gemini to reject the request. The provider now expresses large array bounds in the schema description while retaining full Pydantic validation of every response. A regression test verifies that a response exceeding the original bound is still rejected. Missing-model and upstream deadline errors now have actionable messages, and a successful retry clears the frontend's stale error.

## Scope and next stage

This is a local runnable frontend, not a public deployment. `STORY_API_URL` must point to a reachable FastAPI service if the frontend is deployed elsewhere. The synchronous model workflow can take up to 330 seconds; hosting platforms may impose shorter limits even though the route requests a 360-second budget. Stage 8 should address durable jobs, limits, observability, and deployment before public use.

Cloud database provisioning is environment setup rather than source code: the new Neon database has schema version 2, while its credentials remain local. The free cloud plan does not make Gemini usage free.
