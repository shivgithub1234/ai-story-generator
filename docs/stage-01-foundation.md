# Stage 1 — Backend foundation

## What you have built

A small HTTP API with a health check, interactive documentation, and validation for future story-generation inputs. This is the first working slice of the backend, before paid model calls or database setup.

An API lets another program, such as the future website, send a request and receive structured data. FastAPI handles HTTP routing. Pydantic checks that the request follows our contract. Uvicorn runs the application as a local server.

## Follow a request through the code

1. A client sends JSON to `POST /api/story-requests/validate`.
2. FastAPI reads the `StoryRequest` type in `main.py`.
3. Pydantic applies the rules in `schemas.py`: required premise and genre, allowed languages, bounded word count, and optional tone.
4. Invalid input returns HTTP 422 before the route runs. Valid input reaches the route with surrounding whitespace removed from premise and tone.
5. The route returns `ValidationResponse`, containing the validated request and a message explaining that generation is not implemented yet.

`GET /health` returns `{"status":"ok","version":"0.1.0"}`. It checks that the API responds, not the health of future databases or model providers.

## Why these choices

- Validation catches missing or oversized inputs before later stages spend money on model calls.
- Unknown fields are rejected so a misspelled option cannot silently disappear.
- The source package is separate from tests, leaving room for workflow and service modules later.
- A validation-only route makes this milestone usable without pretending a story has been generated or saved.
- The dependency snapshot lets another developer install the versions tested at this checkpoint.

## Try it yourself

Follow the README to start the server. In `/docs`, send the example request and inspect HTTP 200. Replace the premise with spaces or set `target_words` to 5000 and inspect HTTP 422. Try omitting language and tone to see defaults. Then run the verification commands.

The tests exercise requests through the real application interface, including invalid fields and strict word-count types. See the official [FastAPI testing guide](https://fastapi.tiangolo.com/tutorial/testing/) for the underlying approach.

## Save and push this checkpoint

Run these commands from the repository root after reviewing the files:

```powershell
git status
git add .gitignore README.md backend docs
git diff --cached --stat
git commit -m "feat: establish FastAPI foundation and story input validation"
git branch -M main
```

Create an empty GitHub repository named `ai-story-generator` without adding a README, license, or gitignore on GitHub. Replace `YOUR_USERNAME` below with your GitHub username:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/ai-story-generator.git
git push -u origin main
```

If you already configured a remote, inspect it with `git remote -v` and use that existing remote instead of adding it again. If Git asks for identity, configure your own name and email before retrying the commit. GitHub may prompt you to sign in when pushing.

For later milestones, review changes, run verification, commit with the milestone's message, and use `git push`. No remote has been configured or pushed by this stage's implementation.

## What comes next

Stage 2 adds the model-provider adapter, versioned planner prompt, structured outline response, and generation error handling. The validated input contract built here becomes the input to that operation.
