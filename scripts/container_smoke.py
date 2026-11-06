"""Only run inside the disposable Compose CI stack; never against Neon."""

import os
import time
from uuid import uuid4

from sqlalchemy.engine import make_url

from story_api.auth import Identity, resolve_user
from story_api.database import get_engine
from story_api.schemas import StoryRequest
from story_api.storage import StoryStore

assert os.environ.get("STORY_ENV") == "development"
assert os.environ.get("STORY_PROVIDER") == "demo"
assert make_url(os.environ["DATABASE_URL"]).host == "database"
assert make_url(os.environ["DATABASE_URL"]).database == "story_ci"
engine = get_engine()
owner = resolve_user(engine, Identity("https://ci.invalid", str(uuid4())))
store = StoryStore(engine, owner.id)
story_id, _, _ = store.start(
    StoryRequest(premise="A librarian discovers a hidden door inside a book.", genre="fantasy"),
    queued=True,
)
for _ in range(60):
    run = store.get(story_id)["latest_run"]
    if run["status"] == "completed":
        assert run["output"]["is_demo"] is True
        print("Container worker generated and persisted the demo story.")
        break
    assert run["status"] != "failed", "Demo worker failed"
    time.sleep(2)
else:
    raise SystemExit("Worker did not complete within 120 seconds")
