"""Fail before serving production traffic when deployment settings are unsafe."""

import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

from story_api.limits import UsageConfigurationError, get_limits


class DeploymentConfigurationError(Exception):
    pass


def validate_runtime():
    load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)
    mode = os.getenv("STORY_ENV", "development")
    if mode not in {"development", "production"}:
        raise DeploymentConfigurationError("STORY_ENV must be development or production.")
    if mode != "production":
        return
    problems = []
    if os.getenv("STORY_ENABLE_UNMETERED_DEV_ENDPOINT", "false").lower() != "false":
        problems.append("Disable STORY_ENABLE_UNMETERED_DEV_ENDPOINT.")
    if os.getenv("STORY_PROVIDER") != "gemini":
        problems.append("Set STORY_PROVIDER=gemini for production.")
    for name in ("GEMINI_API_KEY", "GEMINI_MODEL", "AUTH_AUDIENCE"):
        if not os.getenv(name, "").strip():
            problems.append(f"Set {name}.")
    for name in ("AUTH_ISSUER", "AUTH_JWKS_URL", "AUTH_AUTHORIZED_PARTIES"):
        values = os.getenv(name, "").split(",")
        for value in values:
            parsed = urlparse(value.strip())
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.hostname in {"localhost", "127.0.0.1", "::1"}
                or parsed.hostname.endswith(".clerk.accounts.dev")
                or (
                    name == "AUTH_AUTHORIZED_PARTIES"
                    and (parsed.path != "" or parsed.query or parsed.fragment)
                )
            ):
                problems.append(f"Use a production HTTPS URL for {name}.")
    try:
        url = make_url(os.getenv("DATABASE_URL", ""))
        if (
            url.drivername not in {"postgresql", "postgresql+psycopg"}
            or not url.host
            or url.query.get("sslmode") not in {"require", "verify-ca", "verify-full"}
        ):
            raise ValueError()
    except Exception:
        problems.append("Use a PostgreSQL DATABASE_URL with sslmode=require or stricter.")
    try:
        get_limits()
    except UsageConfigurationError:
        problems.append("Set valid positive usage limits.")
    if problems:
        raise DeploymentConfigurationError(" ".join(problems))


if __name__ == "__main__":
    try:
        validate_runtime()
        print("Deployment configuration check passed.")
    except DeploymentConfigurationError as exc:
        raise SystemExit(str(exc))
