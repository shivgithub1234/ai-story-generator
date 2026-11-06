import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from google.genai import errors, types

from story_api import main, providers
from story_api.generation_models import Assessment, Outline
from story_api.providers import DemoProvider, GeminiProvider, GenerationError
from story_api.schemas import StoryRequest
from story_api.workflow import generate_story

REQUEST = {"premise": "A detective finds a letter predicting tomorrow's crime.", "genre": "mystery"}


@pytest.fixture(autouse=True)
def isolate_configuration(monkeypatch):
    monkeypatch.setattr(providers, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("STORY_PROVIDER", "demo")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)


def test_demo_runs_both_agents_and_returns_readable_script():
    with TestClient(main.app) as client:
        response = client.post("/api/stories/generate", json=REQUEST)
    assert response.status_code == 200
    body = response.json()
    assert body["is_demo"] is True
    assert body["provider"] == "demo"
    assert [step["step"] for step in body["usage"]] == [
        "planner",
        "writer",
        "evaluator",
        "revision",
        "final_evaluator",
    ]
    assert body["revision_count"] == 1
    assert body["stop_reason"] == "revision_limit_reached"
    assert body["evaluation"]["overall_score"] == 6.4
    assert body["evaluation"]["needs_revision"] is True
    assert len(body["script"]["scenes"]) == len(body["outline"]["scene_beats"]) == 3
    assert body["outline"]["title"] in body["final_text"]
    assert "Mira:" in body["final_text"]
    assert "not AI-generated" in body["warnings"][0]
    assert all(step["input_tokens"] is None for step in body["usage"])


def test_bad_input_never_constructs_provider(monkeypatch):
    def unexpected_provider():
        pytest.fail("Invalid request must not make a paid call")

    monkeypatch.setattr(main, "create_provider", unexpected_provider)
    assert TestClient(main.app).post("/api/stories/generate", json={}).status_code == 422


@pytest.mark.parametrize("provider", ["gemini", "unsupported"])
def test_configuration_errors_do_not_fall_back_to_demo(monkeypatch, provider):
    monkeypatch.setenv("STORY_PROVIDER", provider)
    response = TestClient(main.app).post("/api/stories/generate", json=REQUEST)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "configuration_error"


def test_writer_receives_planner_output_and_original_preferences():
    class RecordingProvider(DemoProvider):
        def __init__(self):
            self.calls = []

        async def generate(self, instructions, payload, schema):
            self.calls.append((instructions, payload))
            return await super().generate(instructions, payload, schema)

    provider = RecordingProvider()
    request = StoryRequest(**REQUEST, language="Hindi", tone="Suspenseful")
    result = asyncio.run(generate_story(request, provider))
    assert len(provider.calls) == 5
    assert provider.calls[0][0] != provider.calls[1][0]
    assert provider.calls[1][1]["outline"] == result.outline.model_dump()
    assert provider.calls[1][1]["request"] == request.model_dump()
    assert provider.calls[2][1]["script"] == result.initial_script.model_dump()
    assert provider.calls[2][1]["request"] == request.model_dump()


def test_planner_failure_prevents_writer_call_and_closes_provider(monkeypatch):
    provider = DemoProvider()
    provider.generate = AsyncMock(
        side_effect=GenerationError("invalid_model_output", "Invalid output")
    )
    provider.close = AsyncMock()
    monkeypatch.setattr(main, "create_provider", lambda: provider)
    response = TestClient(main.app).post("/api/stories/generate", json=REQUEST)
    assert response.status_code == 502
    assert provider.generate.await_count == 1
    provider.close.assert_awaited_once()


def test_unknown_dialogue_character_is_rejected():
    class BadWriter(DemoProvider):
        async def generate(self, instructions, payload, schema):
            result = await super().generate(instructions, payload, schema)
            if schema is not Outline:
                result.value.scenes[0].dialogue[0].speaker = "Unknown character"
            return result

    with pytest.raises(GenerationError, match="preserve"):
        asyncio.run(generate_story(StoryRequest(**REQUEST), BadWriter()))


@pytest.fixture
def gemini(monkeypatch):
    call = AsyncMock()
    async_client = SimpleNamespace(
        models=SimpleNamespace(generate_content=call), aclose=AsyncMock()
    )
    monkeypatch.setattr(
        providers.genai,
        "Client",
        lambda **kwargs: SimpleNamespace(
            aio=async_client,
            close=lambda: None,
        ),
    )
    return GeminiProvider("test-key-not-a-real-secret", "test-model"), call


def test_gemini_validates_output_and_reports_usage(gemini):
    provider, call = gemini
    outline = asyncio.run(DemoProvider().generate("", {}, Outline)).value
    call.return_value = SimpleNamespace(
        candidates=[SimpleNamespace(finish_reason=types.FinishReason.STOP)],
        text=outline.model_dump_json(),
        usage_metadata=SimpleNamespace(prompt_token_count=40, candidates_token_count=80),
    )
    result = asyncio.run(provider.generate("Planner instructions", {"request": REQUEST}, Outline))
    assert result.value == outline
    assert (result.input_tokens, result.output_tokens) == (40, 80)
    config = call.call_args.kwargs["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == Outline.model_json_schema()
    assert config.system_instruction == "Planner instructions"


@pytest.mark.parametrize("text", ["not json", "{}", '{"title": "Missing fields"}'])
def test_gemini_malformed_output_is_rejected(gemini, text):
    provider, call = gemini
    call.return_value = SimpleNamespace(
        candidates=[SimpleNamespace(finish_reason=types.FinishReason.STOP)],
        text=text,
    )
    with pytest.raises(GenerationError) as error:
        asyncio.run(provider.generate("", {}, Outline))
    assert error.value.code == "invalid_model_output"


@pytest.mark.parametrize("reason", [types.FinishReason.MAX_TOKENS, types.FinishReason.SAFETY])
def test_gemini_incomplete_output_is_rejected(gemini, reason):
    provider, call = gemini
    call.return_value = SimpleNamespace(candidates=[SimpleNamespace(finish_reason=reason)])
    with pytest.raises(GenerationError) as error:
        asyncio.run(provider.generate("", {}, Outline))
    assert error.value.code == "incomplete_output"


@pytest.mark.parametrize(
    "exception, status",
    [
        (httpx.ReadTimeout("private upstream details"), 504),
        (httpx.ConnectError("private upstream details"), 503),
        (errors.APIError(429, {"error": {"message": "private upstream details"}}), 429),
        (errors.APIError(403, {"error": {"message": "private upstream details"}}), 502),
    ],
)
def test_provider_failures_return_safe_errors(gemini, exception, status):
    provider, call = gemini
    call.side_effect = exception
    with pytest.raises(GenerationError) as error:
        asyncio.run(provider.generate("", {}, Outline))
    assert error.value.status == status
    assert "private upstream details" not in error.value.message


def test_workflow_timeout_closes_provider(monkeypatch):
    provider = DemoProvider()
    provider.close = AsyncMock()
    monkeypatch.setattr(main, "create_provider", lambda: provider)
    monkeypatch.setattr(main, "generate_story", AsyncMock(side_effect=TimeoutError))
    response = TestClient(main.app).post("/api/stories/generate", json=REQUEST)
    assert response.status_code == 504
    provider.close.assert_awaited_once()


@pytest.mark.parametrize("schema", [Outline, Assessment])
def test_real_gemini_sdk_serializes_schema_and_parses_mock_http_response(monkeypatch, schema):
    """Exercise the installed SDK without credentials or an external network request."""
    outline = asyncio.run(DemoProvider().generate("", {}, schema)).value
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [{"text": outline.model_dump_json()}],
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 30, "candidatesTokenCount": 50},
            },
        )

    original_client = providers.genai.Client

    def client_factory(**kwargs):
        kwargs["http_options"].httpx_async_client = httpx.AsyncClient(
            transport=httpx.MockTransport(respond),
        )
        return original_client(**kwargs)

    monkeypatch.setattr(providers.genai, "Client", client_factory)

    async def run():
        provider = GeminiProvider("test-key-not-a-real-secret", "test-model")
        try:
            return await provider.generate("Agent instructions", {"request": REQUEST}, schema)
        finally:
            await provider.close()

    result = asyncio.run(run())
    assert result.value == outline
    assert result.output_tokens == 50
    assert len(requests) == 1
    assert requests[0]["generationConfig"]["responseMimeType"] == "application/json"
    assert "responseJsonSchema" in requests[0]["generationConfig"]
