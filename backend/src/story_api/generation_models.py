"""Validated contracts between agents, provider, and API."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]


class StructuredModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Character(StructuredModel):
    name: Text
    goal: Text
    traits: Text


class Outline(StructuredModel):
    title: Text
    setting: Text
    conflict: Text
    characters: list[Character] = Field(min_length=1, max_length=6)
    scene_beats: list[Text] = Field(min_length=3, max_length=6)


class Dialogue(StructuredModel):
    speaker: Text
    text: Text


class Scene(StructuredModel):
    heading: Text
    narration: Text
    dialogue: list[Dialogue] = Field(min_length=1, max_length=60)


class Script(StructuredModel):
    title: Text
    scenes: list[Scene] = Field(min_length=3, max_length=6)


class StepUsage(BaseModel):
    step: Literal["planner", "writer", "evaluator"]
    elapsed_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None


class DimensionRating(StructuredModel):
    score: int = Field(ge=1, le=10, strict=True)
    explanation: Text
    evidence: Text
    scene_numbers: list[Annotated[int, Field(ge=1, le=6, strict=True)]] = Field(
        min_length=1, max_length=6
    )


class Assessment(StructuredModel):
    narrative_coherence: DimensionRating
    character_consistency: DimensionRating
    repetition_avoidance: DimensionRating
    language_quality: DimensionRating
    instruction_adherence: DimensionRating
    summary: Text
    revision_suggestions: list[Text] = Field(min_length=1, max_length=5)


class EvaluationReport(BaseModel):
    rubric_version: str
    assessment: Assessment
    overall_score: float
    revision_threshold: float
    needs_revision: bool


class GenerationResponse(BaseModel):
    run_id: str
    status: Literal["completed"] = "completed"
    provider: str
    model: str
    is_demo: bool
    prompt_version: str
    outline: Outline
    script: Script
    evaluation: EvaluationReport
    final_text: str
    usage: list[StepUsage]
    warnings: list[str]
