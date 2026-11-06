import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from story_api import main
from story_api.evaluation import DIMENSIONS
from story_api.generation_models import Assessment, Script
from story_api.providers import DemoProvider, GenerationError, ModelResult
from story_api.schemas import StoryRequest
from story_api.workflow import generate_story

REQUEST = StoryRequest(
    premise="A detective finds a letter predicting tomorrow's crime.", genre="mystery"
)


class ScoredProvider(DemoProvider):
    """Controlled scores exercise graph branches without judging creative quality."""

    def __init__(self, scores):
        self.scores = iter(scores)
        self.calls = []

    async def generate(self, instructions, payload, schema):
        self.calls.append((instructions, payload, schema))
        result = await super().generate(instructions, payload, schema)
        if schema is Assessment:
            data = result.value.model_dump()
            for name, score in zip(DIMENSIONS, next(self.scores), strict=True):
                data[name]["score"] = score
            return ModelResult(Assessment.model_validate(data), input_tokens=10, output_tokens=20)
        return result


@pytest.mark.parametrize("scores", [[8, 8, 8, 8, 8], [4, 7, 8, 8, 8]])
def test_passing_draft_stops_after_three_calls(scores):
    provider = ScoredProvider([scores])
    result = asyncio.run(generate_story(REQUEST, provider))
    assert len(provider.calls) == 3
    assert result.revision_count == 0
    assert result.stop_reason == "quality_passed"
    assert result.script == result.initial_script
    assert result.evaluation == result.initial_evaluation


@pytest.mark.parametrize("scores", [[6, 6, 6, 6, 6], [10, 10, 10, 10, 3]])
def test_either_rule_triggers_one_rewrite_with_feedback(scores):
    provider = ScoredProvider([scores, [8, 8, 8, 8, 8]])
    result = asyncio.run(generate_story(REQUEST, provider))
    assert len(provider.calls) == 5
    assert result.revision_count == 1
    assert result.stop_reason == "quality_passed"
    assert result.initial_evaluation.needs_revision
    assert not result.evaluation.needs_revision
    rewrite = provider.calls[3][1]
    assert rewrite["previous_script"] == result.initial_script.model_dump()
    assert rewrite["feedback"] == result.initial_evaluation.model_dump()
    assert rewrite["request"] == REQUEST.model_dump()
    assert rewrite["outline"] == result.outline.model_dump()
    assert provider.calls[3][0] != provider.calls[1][0]
    # Final judge sees the new draft, without previous scores that could anchor its judgment.
    assert provider.calls[4][1]["script"] == result.script.model_dump()
    assert "feedback" not in provider.calls[4][1]
    assert result.initial_script != result.script
    assert "departure bell" not in result.initial_script.scenes[0].narration
    assert "departure bell" in result.final_text
    assert [step.step for step in result.usage] == [
        "planner",
        "writer",
        "evaluator",
        "revision",
        "final_evaluator",
    ]
    assert result.usage[-1].input_tokens == 10


@pytest.mark.parametrize("final_scores", [[2, 2, 2, 2, 2], [10, 10, 10, 10, 3]])
def test_still_weak_or_worse_revision_stops_at_five_calls(final_scores):
    provider = ScoredProvider([[6, 6, 6, 6, 6], final_scores])
    result = asyncio.run(generate_story(REQUEST, provider))
    assert len(provider.calls) == 5
    assert result.revision_count == 1
    assert result.evaluation.needs_revision
    assert result.stop_reason == "revision_limit_reached"
    assert result.script != result.initial_script


@pytest.mark.parametrize("failure_step", ["rewrite", "final_judge"])
def test_revision_stage_failure_returns_error_and_closes_provider(monkeypatch, failure_step):
    class FailingProvider(ScoredProvider):
        async def generate(self, instructions, payload, schema):
            if (failure_step == "rewrite" and "previous_script" in payload) or (
                failure_step == "final_judge" and len(self.calls) == 4
            ):
                raise GenerationError("provider_timeout", "Gemini timed out.", 504)
            return await super().generate(instructions, payload, schema)

    provider = FailingProvider([[6, 6, 6, 6, 6]])
    provider.close = AsyncMock()
    monkeypatch.setattr(main, "create_provider", lambda: provider)
    response = TestClient(main.app).post("/api/stories/generate", json=REQUEST.model_dump())
    assert response.status_code == 504
    assert "script" not in response.json()
    provider.close.assert_awaited_once()


def test_revised_script_still_must_follow_outline():
    class InvalidRevision(ScoredProvider):
        async def generate(self, instructions, payload, schema):
            result = await super().generate(instructions, payload, schema)
            if schema is Script and "previous_script" in payload:
                result.value.scenes[0].dialogue[0].speaker = "Unknown character"
            return result

    provider = InvalidRevision([[6, 6, 6, 6, 6]])
    with pytest.raises(GenerationError, match="preserve"):
        asyncio.run(generate_story(REQUEST, provider))
    assert len(provider.calls) == 4
