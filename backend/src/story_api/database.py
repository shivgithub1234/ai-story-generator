"""PostgreSQL engine and an explicit, transactional initial schema migration."""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class DatabaseConfigurationError(Exception):
    pass


@lru_cache(maxsize=1)
def get_engine():
    load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)
    raw = os.getenv("DATABASE_URL", "").strip()
    if not raw:
        raise DatabaseConfigurationError("Set DATABASE_URL for saved-story operations.")
    try:
        url = make_url(raw)
        if url.drivername not in {"postgresql", "postgresql+psycopg"}:
            raise ValueError("Unsupported database")
        url = url.set(drivername="postgresql+psycopg")
    except Exception as exc:
        raise DatabaseConfigurationError("DATABASE_URL must be a valid PostgreSQL URL.") from exc
    return create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})


def migrate(engine):
    # Imports register the tables. Future schema changes must add explicit migrations.
    from story_api import storage

    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(531905)"))
        connection.execute(
            text("CREATE TABLE IF NOT EXISTS story_schema_version (version INTEGER PRIMARY KEY)")
        )
        version = connection.execute(text("SELECT max(version) FROM story_schema_version")).scalar()
        if version is None:
            storage.Base.metadata.create_all(connection)
            connection.execute(text("INSERT INTO story_schema_version (version) VALUES (2)"))
        elif version == 1:
            storage.AppUser.__table__.create(connection)
            connection.execute(
                text(
                    "ALTER TABLE story_projects ADD COLUMN owner_id VARCHAR(36) "
                    "REFERENCES app_users(id)"
                )
            )
            connection.execute(
                text("CREATE INDEX ix_story_projects_owner_id ON story_projects(owner_id)")
            )
            connection.execute(text("INSERT INTO story_schema_version (version) VALUES (2)"))
        elif version != 2:
            raise DatabaseConfigurationError("Unsupported database schema version.")


if __name__ == "__main__":
    try:
        migrate(get_engine())
        print(
            "Database schema ready (version 2). Legacy stories remain unassigned and inaccessible."
        )
    except Exception:
        raise SystemExit("Database initialization failed. Check DATABASE_URL and database access.")
