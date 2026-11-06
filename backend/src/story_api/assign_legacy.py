"""Explicit local-admin ownership assignment; never exposed as an HTTP endpoint."""

import argparse
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from story_api.database import get_engine
from story_api.storage import AppUser, StoryProject


def assign(engine, story_id: str, user_id: str):
    with Session(engine) as session, session.begin():
        if session.get(AppUser, user_id) is None:
            raise ValueError("User must sign in and call /api/auth/me before assignment.")
        changed = session.execute(
            update(StoryProject)
            .where(
                StoryProject.id == story_id,
                StoryProject.owner_id.is_(None),
            )
            .values(owner_id=user_id)
        )
        if changed.rowcount != 1:
            raise ValueError("Story does not exist or already has an owner; no change made.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Assign one verified legacy story to an existing user."
    )
    parser.add_argument("--story-id", type=UUID, required=True)
    parser.add_argument("--user-id", type=UUID, required=True)
    args = parser.parse_args()
    try:
        assign(get_engine(), str(args.story_id), str(args.user_id))
        print("Legacy story assigned.")
    except ValueError as exc:
        raise SystemExit(str(exc))
    except Exception:
        raise SystemExit("Assignment failed; check database configuration.")
