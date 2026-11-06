"""The input contract shared by validation and future story generation."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Premise = Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=2000)]
Tone = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class StoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    premise: Premise
    genre: Literal["mystery", "fantasy", "science-fiction", "drama", "comedy", "horror"]
    language: Literal["English", "Hindi"] = "English"
    target_words: int = Field(default=1000, ge=200, le=3000, strict=True)
    tone: Tone | None = None


class ValidationResponse(BaseModel):
    valid: Literal[True] = True
    request: StoryRequest
    message: str = "Input is valid. Submit it to /api/stories/generate to generate a draft."


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str = "0.3.0"
