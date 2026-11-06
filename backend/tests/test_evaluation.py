import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from story_api import main
from story_api.evaluation import DIMENSIONS, build_report
from story_api.generation_models import Assessment
from story_api.providers import DemoProvider, GenerationError


def sample_assessment():
    return asyncio.run(DemoProvider().generate("", {}, Assessment)).value


@pytest.mark.parametrize("score, expected", [(1, True), (6, True), (7, False), (10, False)])
def test_threshold_boundary_and_application_owned_average(score, expected):
    data = sample_assessment().model_dump()
    for dimension in DIMENSIONS:
        data[dimension]["score"] = score
    report = build_report(Assessment.model_validate(data), 3)
    assert report.overall_score == score
    assert report.needs_revision is expected
    assert report.revision_threshold == 7.0


@pytest.mark.parametrize("score", [0, 11, 7.5, "8", True])
def test_invalid_scores_are_rejected(score):
    data = sample_assessment().model_dump()
    data["narrative_coherence"]["score"] = score
    with pytest.raises(ValidationError):
        Assessment.model_validate(data)


@pytest.mark.parametrize("field", ["evidence", "explanation", "scene_numbers"])
def test_every_score_requires_support(field):
    data = sample_assessment().model_dump()
    del data["language_quality"][field]
    with pytest.raises(ValidationError):
        Assessment.model_validate(data)


def test_missing_dimension_and_model_supplied_aggregate_are_rejected():
    data = sample_assessment().model_dump()
    del data["instruction_adherence"]
    with pytest.raises(ValidationError):
        Assessment.model_validate(data)
    data = sample_assessment().model_dump()
    data["overall_score"] = 10
    with pytest.raises(ValidationError):
        Assessment.model_validate(data)


def test_nonexistent_scene_reference_is_rejected():
    data = sample_assessment().model_dump()
    data["language_quality"]["scene_numbers"] = [4]
    with pytest.raises(GenerationError, match="does not exist"):
        build_report(Assessment.model_validate(data), 3)


@pytest.mark.parametrize("dimension", DIMENSIONS)
@pytest.mark.parametrize("low_score, expected", [(3, True), (4, False)])
def test_individual_dimension_floor_even_with_high_average(dimension, low_score, expected):
    data = sample_assessment().model_dump()
    for name in DIMENSIONS:
        data[name]["score"] = 10
    data[dimension]["score"] = low_score
    report = build_report(Assessment.model_validate(data), 3)
    assert report.overall_score >= 7
    assert report.dimension_threshold == 4
    assert report.needs_revision is expected


def test_exact_average_seven_and_dimension_four_pass():
    data = sample_assessment().model_dump()
    for name, score in zip(DIMENSIONS, [4, 7, 8, 8, 8], strict=True):
        data[name]["score"] = score
    report = build_report(Assessment.model_validate(data), 3)
    assert report.overall_score == 7
    assert not report.needs_revision


def test_failed_judge_returns_error_and_closes_provider(monkeypatch):
    class FailingJudge(DemoProvider):
        async def generate(self, instructions, payload, schema):
            if schema is Assessment:
                raise GenerationError("invalid_model_output", "Invalid evaluation")
            return await super().generate(instructions, payload, schema)

    provider = FailingJudge()
    provider.close = AsyncMock()
    monkeypatch.setattr(main, "create_provider", lambda: provider)
    result = TestClient(main.app).post(
        "/api/stories/generate",
        json={
            "premise": "A detective finds a letter predicting tomorrow's crime.",
            "genre": "mystery",
        },
    )
    assert result.status_code == 502
    assert "evaluation" not in result.json()
    provider.close.assert_awaited_once()
