# Stage 8d — Free hosted portfolio demo

Deployment status: portfolio demo live at https://ai-story-generator-tau-ten.vercel.app on Vercel Hobby, deployed from `1055dff` on November 6, 2026.

## Observed verification

- Production deployment `8EG4CoDPvRfttHGpWesiQkK6njhg` is Ready. Both Python images and the frontend built successfully.
- GitHub Actions run https://github.com/shivgithub1234/ai-story-generator/actions/runs/42265581865 passed both jobs on the deployed commit.
- The public page and three sampled static assets returned HTTP 200. Unauthenticated stories and account requests returned HTTP 401.
- Clerk sign-in succeeded on the hosted origin. The personal library loaded three existing stories from Neon. A saved story rendered its edits and evaluation.
- The cloud worker reports one ready instance in iad1 and logs `Worker started; waiting for queued stories`. The local worker was stopped.
- A new hosted Gemini generation was **not verified**: the account had already consumed the demo's three-request rolling allowance through earlier local runs against the same database. The UI correctly disabled new generation. No quota records were reset or bypassed.

The first cloud build exposed a legacy 360-second API proxy duration, which exceeded Hobby's limit. The proxy now has a 60-second duration and a 55-second upstream timeout; long story generation remains in the worker.

The Vercel project stays at the repository root. `vercel.json` defines the native Next.js frontend, a private container API reached through `STORY_API_URL`, and one 1 GiB worker daemon in iad1. Both Python workloads build `Dockerfile.vercel` from the repository root; the Compose Dockerfiles remain unchanged. Only the frontend has a public route. The API still checks Clerk bearer tokens and ownership.

## Demo environment

Use the Hobby plan without upgrades. Set project variables for the production deployment target (the stable public URL), while setting `STORY_ENV=development` because this portfolio demo uses Clerk test credentials. Vercel's target name does not make these credentials production-ready.

Required variables: `DATABASE_URL`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `AUTH_ISSUER`, `AUTH_JWKS_URL`, `AUTH_AUDIENCE=story-api`, `AUTH_AUTHORIZED_PARTIES=https://ai-story-generator-tau-ten.vercel.app`, and `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`. Set `PORT=8000`, `STORY_PROVIDER=gemini`, `STORY_ENABLE_UNMETERED_DEV_ENDPOINT=false`, `STORY_REQUESTS_PER_24H=3`, and `STORY_MAX_ACTIVE_JOBS=1`. Store secrets only in hosting environment settings. Do not manually set `STORY_API_URL`; Vercel supplies its private binding.

Run the existing migration explicitly before releasing the worker. No migration runs during the image build. Confirm Gemini and Neon remain on free plans: per-user application limits do not cap total provider billing.

## Free-tier constraints

Vercel Services, Container Runtime, and Daemons are beta features. Hobby daemon quotas are 5 active CPU-hours and 420 GB-hours monthly, shared across the team. One 1 GiB worker can run at most about 420 hours (17.5 days) before its memory allowance is exhausted, less if other daemons consume the allowance. Hobby stops daemons at the quota instead of billing overages. This is a limited demo, not a promise of uninterrupted monthly availability.

Continuous database polling also keeps Neon compute active and can exhaust its free allowance. Stop the worker from the Daemons dashboard between demonstrations, or set its instance count to zero and redeploy. Never use artificial HTTP keep-alives to evade free-tier sleeping. When the worker is stopped, new stories remain queued until a worker resumes; the library can still display saved results while database/API quotas allow.

Sources: https://vercel.com/docs/daemons/limits and https://vercel.com/docs/services

## Verification before sharing

Check the deployed page and assets, unauthenticated API rejection, Clerk sign-in, personal library, one short queued Gemini story through the hosted worker, and saved story refresh. Verify worker logs and database persistence. Do not claim success based only on a successful frontend build.

## Live generation verification after account reset

On November 6, 2026, schema 4 and the account-specific reset feature were deployed from `3488d24`. Only the requesting account's allowance was reset; history was preserved. The hosted UI showed 3/3 remaining, accepted a 200-word-target fantasy prompt, displayed evaluation progress, then rendered **The Star-Tender's Dawn** with a 9.0/10 evaluation and no revision recommended. The allowance dropped to 2/3 and active jobs returned to zero. The local worker was stopped, so this verifies the hosted worker path. This supersedes the earlier quota-blocked verification limitation above.
