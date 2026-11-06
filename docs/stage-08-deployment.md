# Stage 8c — Deployment preparation

This checkpoint prepares deployment artifacts. It does not provision a host, register a domain, publish images, or deploy the app publicly.

## What runs where

| Service | Purpose | Public port |
| --- | --- | --- |
| Frontend | Next.js UI and bearer-authenticated proxy | 3000, bound to localhost by default |
| API | Auth, usage limits, queue submission, saved stories | None in Compose; internal port 8000 |
| Worker | Long-running Gemini generation process | None |
| Migration job | Configuration check and schema initialization | None; exits after completion |
| PostgreSQL | Persistent application data and queue | External managed database, such as Neon |

The frontend talks to `http://api:8000` over the Compose network. The browser never receives that internal URL or database/model credentials. The API and worker share the same backend image and database. Both images run as non-root users. `.dockerignore` excludes local secrets, Git history, virtual environments, dependencies, and build output from the build context.

Next.js uses standalone output, with its static assets copied into the runtime image. Its Clerk **publishable key is a build argument** and is embedded in client JavaScript. Changing it requires rebuilding the frontend. Secret keys are runtime environment settings for the backend services only. The backend reuses the existing pinned requirements lock, including its development tools; base-image tags should be reviewed and pinned to digests for release reproducibility.

## Prepare production settings

Install Docker Engine/Desktop with Compose v2 on the deployment host. Use a host that supports an always-running worker, rather than a worker inside a short-lived HTTP function. Copy `deploy/.env.example` to `deploy/.env`; it is ignored by Git. Fill the placeholders locally or use your host's secret manager. Do not paste these values into commits, logs, or screenshots.

- Use a production Clerk instance, its production issuer/JWKS URL, and audience `story-api` in session tokens.
- Set `AUTH_AUTHORIZED_PARTIES` to the exact HTTPS frontend origin, without a trailing slash, path, or wildcard. Configure Clerk's allowed URLs and OAuth redirect settings for that domain.
- Use that instance's `pk_live_...` publishable key to build the frontend. No Clerk secret key is needed by the current client-SDK architecture.
- Set the Gemini key and a model available to your account.
- Use a PostgreSQL URL with `sslmode=require` or stronger. `verify-full` additionally checks the server identity when your provider supports it.
- Keep `STORY_ENABLE_UNMETERED_DEV_ENDPOINT` disabled; Compose forces it to `false`.
- Review the 10-request rolling allowance and 2-active-job default. These are not monetary budgets or global abuse protection.

`STORY_ENV=production` enables startup validation in both API and worker. It rejects development Clerk domains, insecure auth URLs, missing model settings, invalid limits, non-SSL database URLs, and the unmetered endpoint. The frontend image build rejects a non-live Clerk key in production mode. These checks validate configuration shape; they do not verify credentials with external services.

For a container rehearsal with existing development Clerk credentials, set `STORY_ENV=development` and keep the frontend bound to localhost. Never present a development-key rehearsal as production verification.

## Build and start

Run from the repository root. Commands work in PowerShell or a POSIX shell:

```text
docker compose --env-file deploy/.env config --quiet
docker compose --env-file deploy/.env build
docker compose --env-file deploy/.env run --rm migrate
docker compose --env-file deploy/.env up -d
docker compose --env-file deploy/.env ps
docker compose --env-file deploy/.env logs --tail=100 api worker
```

Use `config --quiet`: plain `docker compose config` can print interpolated secrets. Migration is explicit and transactional. Startup dependencies also ensure migration succeeds before API/worker startup, and API readiness before frontend startup. Dependencies govern startup only; they are not a database failover mechanism. [Docker startup ordering](https://docs.docker.com/compose/how-tos/startup-order).

Compose exposes only `127.0.0.1:3000` by default. Put a TLS reverse proxy on that host in front of it, routing the chosen domain to the frontend. On a managed container platform, use its HTTPS ingress, private service discovery, and secret storage. Do not expose the database or worker to the public internet. Preserve the original frontend host/protocol when proxying so same-origin requests work correctly.

The Next.js artifact follows [standalone output guidance](https://nextjs.org/docs/app/api-reference/config/next-config-js/output). If choosing separate hosting later, deploy the frontend there with its build-time key and set the server-only `STORY_API_URL` to the reachable API service; the worker still needs its own persistent process.

## Checks and monitoring

- `/health` reports API process liveness without calling external services.
- `/ready` returns 200 only if PostgreSQL is reachable and schema version 3 is present; otherwise it returns a generic 503 without connection details. It does not call Gemini or check whether a worker is alive.
- Compose restarts exited API, frontend, and worker processes. An `unhealthy` status alone does not restart a still-running container.
- Watch worker logs and the age of queued jobs. A running API does not guarantee a working queue consumer. Worker metrics, alerts, and queue-age monitoring are still follow-up work.
- After deployment, sign in with two accounts, verify isolation, submit a short real story, refresh while queued/running, inspect feedback, save/reopen an edit, and check usage limits. CI's demo smoke test does not verify real Clerk or Gemini credentials.

## Scale, upgrade, and rollback

Add workers using the same image/configuration:

```text
docker compose --env-file deploy/.env up -d --scale worker=3
```

Each worker handles one job at a time. More workers increase concurrent model calls and database connections. They share PostgreSQL claims and leases; admission limits remain per account. Start with one and increase only after measuring latency, quotas, and cost.

For an upgrade, save the previous Git commit and image tag, back up the managed database, set `RELEASE_TAG` to the new commit, build, run migration, and recreate services with `up -d`. The migration job is repeatable. Keep the previous images until the new version passes the hosted checks.

On failure, restore the previous compatible image tags/configuration and recreate services. Do not blindly downgrade a schema or restore a backup over new user data. This checkpoint adds no schema migration beyond version 3. SIGTERM cancels a worker cleanly; any unfinished job becomes eligible for recovery after its lease expires and may repeat model calls. For a quiet deployment, let active jobs finish before stopping workers.

## CI and verification scope

`.github/workflows/ci.yml` runs on pushes and pull requests. It runs backend tests with disposable PostgreSQL, frontend tests/build, then builds and starts the Compose stack using demo mode and a separate disposable database. `scripts/container_smoke.py` submits a job and checks that the separate worker persists a completed demo result. It refuses production mode, real providers, and databases other than the named CI database. No real Clerk or Gemini keys are supplied to CI, and no images are published.

Docker is not installed in the current development environment. Therefore container builds, Compose startup, and the GitHub Actions workflow have **not yet been executed here**. Local application tests and standalone build checks are recorded separately. Before a public release, require the Linux container job to pass, verify the configured services end to end, and add deployment-specific abuse protection and operational monitoring.

Local verification: 136 backend tests passed against isolated PostgreSQL; the production standalone build and TypeScript checks passed. Running the generated standalone server returned 200 for its page and three sampled static assets, and 401 for an unauthenticated private API request. Deployment and worker tests were also rerun after the final startup/shutdown changes. YAML parsing succeeded; this is not a substitute for Docker Compose validation.
