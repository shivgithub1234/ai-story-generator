"""Server-owned admission policy; retries never create new quota entries."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class UsageConfigurationError(Exception):
    pass


class UsageLimitExceeded(Exception):
    def __init__(self, code, message, usage):
        self.code, self.message, self.usage = code, message, usage


@dataclass(frozen=True)
class UsageLimits:
    requests_per_24h: int
    active_jobs: int


def get_limits():
    load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)
    try:
        daily = int(os.getenv("STORY_REQUESTS_PER_24H", "10"))
        active = int(os.getenv("STORY_MAX_ACTIVE_JOBS", "2"))
        if not 1 <= daily <= 10000 or not 1 <= active <= 100:
            raise ValueError()
        return UsageLimits(daily, active)
    except ValueError as exc:
        raise UsageConfigurationError() from exc
