# Implementation roadmap

Each milestone should be runnable, verified, explained, and committed before advancing. Commit dates reflect when the work actually happens.

| Stage | Deliverable | Completion check |
| --- | --- | --- |
| 1 | FastAPI skeleton, typed story input, documentation | Health check and validation tests pass |
| 2 | Gemini adapter and LangGraph Planner → Writer | Outline becomes scenes; offline tests pass; live run requires local Gemini configuration |
| 3 | LLM-as-a-judge evaluator | Rubric scores, evidence, and actionable feedback returned |
| 4 | Feedback-based regeneration | Writer applies feedback; at most one automatic rewrite and final evaluation |
| 5 | PostgreSQL persistence | Stories, drafts, evaluations, and run history survive restart |
| 6 | Clerk authentication and user ownership | Verified tokens; cross-user access denied; legacy stories protected |
| 7 | Next.js interface | User can create, review, edit, and save a story |
| 8a (implemented) | Background jobs and progress | Durable PostgreSQL queue, worker leases/recovery, bounded retries, refresh-safe dashboard |
| 8b (implemented) | Per-user usage limits | Atomic rolling 24-hour allowances, active-job limits, personal usage display |
| 8c (verified) | Deployment artifacts | Docker/Compose, production checks, readiness, passing Linux CI and worker smoke test, rollout runbook |
| 8d (live demo) | Vercel Hobby hosting | Sign-in, library, saved story, worker startup verified; new hosted generation pending allowance reset |
| 9 (optional) | MCP tools, resources, and prompts | A client discovers and invokes shared application capabilities |

Google Gemini is the selected live provider. Stage 2 includes an explicit offline fixture mode; live validation requires a locally configured key and model. Core generation, evaluation, and feedback-based regeneration take priority over persistence and UI. Evaluation scores are estimates, and any performance or cost claims must be measured.
