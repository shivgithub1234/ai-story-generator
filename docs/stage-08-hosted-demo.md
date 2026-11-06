# Stage 8d — Free hosted portfolio demo

Deployment status: prepared locally; hosting verification is pending.

The Vercel project stays at the repository root. `vercel.json` defines the native Next.js frontend, a private container API reached through `STORY_API_URL`, and one 1 GiB worker daemon in iad1. Both Python workloads build `Dockerfile.vercel` from the repository root; the Compose Dockerfiles remain unchanged. Only the frontend has a public route. The API still checks Clerk bearer tokens and ownership.

## Demo environment

Use the Hobby plan without upgrades. Set project variables for the production deployment target (the stable public URL), while setting `STORY_ENV=development` because this portfolio demo uses Clerk test credentials. Vercel's target name does not make these credentials production-ready.

Required variables: `DATABASE_URL`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `AUTH_ISSUER`, `AUTH_JWKS_URL`, `AUTH_AUDIENCE=story-api`, `AUTH_AUTHORIZED_PARTIES` (the exact HTTPS demo origin), and `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`. Set `PORT=8000`, `STORY_PROVIDER=gemini`, `STORY_ENABLE_UNMETERED_DEV_ENDPOINT=false`, `STORY_REQUESTS_PER_24H=3`, and `STORY_MAX_ACTIVE_JOBS=1`. Store secrets only in hosting environment settings. Do not manually set `STORY_API_URL`; Vercel supplies its private binding.

Run the existing migration explicitly before releasing the worker. No migration runs during the image build. Confirm Gemini and Neon remain on free plans: per-user application limits do not cap total provider billing.

## Free-tier constraints

Vercel Services, Container Runtime, and Daemons are beta features. Hobby daemon quotas are 5 active CPU-hours and 420 GB-hours monthly, shared across the team. One 1 GiB worker can run at most about 420 hours (17.5 days) before its memory allowance is exhausted, less if other daemons consume the allowance. Hobby stops daemons at the quota instead of billing overages. This is a limited demo, not a promise of uninterrupted monthly availability.

Continuous database polling also keeps Neon compute active and can exhaust its free allowance. Stop the worker from the Daemons dashboard between demonstrations, or set its instance count to zero and redeploy. Never use artificial HTTP keep-alives to evade free-tier sleeping. When the worker is stopped, new stories remain queued until a worker resumes; the library can still display saved results while database/API quotas allow.

Sources: https://vercel.com/docs/daemons/limits and https://vercel.com/docs/services

## Verification before sharing

Check the deployed page and assets, unauthenticated API rejection, Clerk sign-in, personal library, one short queued Gemini story through the hosted worker, and saved story refresh. Verify worker logs and database persistence. Do not claim success based only on a successful frontend build.
