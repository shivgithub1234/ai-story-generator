# Implementation roadmap

Each milestone should be runnable, verified, explained, and committed before advancing. Commit dates reflect when the work actually happens.

| Stage | Deliverable | Completion check |
| --- | --- | --- |
| 1 | FastAPI skeleton, typed story input, documentation | Health check and validation tests pass |
| 2 | Hosted LLM adapter and structured outline generation | A real premise produces a schema-valid outline; malformed responses handled |
| 3 | LangGraph planner and writer | An outline becomes narration and dialogue scenes |
| 4 | Evaluator and bounded revision | Scores and feedback returned; at most one automatic revision |
| 5 | PostgreSQL persistence | Stories, drafts, evaluations, and run history survive restart |
| 6 | Next.js interface | User can create, review, edit, and save a story |
| 7 | Reliability and delivery | Timeouts, logging, workflow failure handling, tests, Docker, demo instructions |
| 8 (optional) | MCP tools, resources, and prompts | A client discovers and invokes shared application capabilities |

Stage 2 will require choosing a hosted model provider and configuring a local API key. Future stages will add tests as their behavior is implemented. Evaluation scores are estimates, and any performance or cost claims must be measured.
