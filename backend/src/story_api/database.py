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
            connection.execute(text("INSERT INTO story_schema_version (version) VALUES (3)"))
            version = 3
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
            version = 2
        if version == 2:
            for definition in (
                "background BOOLEAN NOT NULL DEFAULT false",
                "stage VARCHAR(30) NOT NULL DEFAULT 'queued'",
                "attempt INTEGER NOT NULL DEFAULT 0",
                "lease_token VARCHAR(36)",
                "available_at TIMESTAMPTZ",
            ):
                connection.execute(
                    text(f"ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS {definition}")
                )
            connection.execute(text("UPDATE workflow_runs SET stage = status WHERE NOT background"))
            connection.execute(text("INSERT INTO story_schema_version (version) VALUES (3)"))
        elif version != 3:
            raise DatabaseConfigurationError("Unsupported database schema version.")
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_workflow_queue "
                "ON workflow_runs (available_at, started_at) "
                "WHERE background AND status IN ('queued', 'running')"
            )
        )


if __name__ == "__main__":
    try:
        migrate(get_engine())
        print(
            "Database schema ready (version 3). Legacy stories remain unassigned and inaccessible."
        )
    except Exception:
        raise SystemExit("Database initialization failed. Check DATABASE_URL and database access.")
