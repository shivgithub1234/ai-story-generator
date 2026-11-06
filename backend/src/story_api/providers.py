"""Provider adapter. Demo data is explicit and never a fallback for Gemini errors."""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeVar

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from story_api.generation_models import (
    Assessment,
    Character,
    Dialogue,
    DimensionRating,
    Outline,
    Scene,
    Script,
)

T = TypeVar("T", bound=BaseModel)


def provider_schema(schema: type[BaseModel]) -> dict:
    """Keep large array bounds out of Gemini's constrained-decoding grammar.

    Nested maxItems=60 expands the writer grammar beyond provider limits. The
    full Pydantic schema still validates every returned response before use.
    """

    def simplify(node):
        if isinstance(node, list):
            return [simplify(value) for value in node]
        if not isinstance(node, dict):
            return node
        result = {key: simplify(value) for key, value in node.items()}
        if result.get("type") == "array" and result.get("maxItems", 0) > 10:
            maximum = result.pop("maxItems")
            result["description"] = (
                f"{result.get('description', '')} At most {maximum} items.".strip()
            )
        return result

    return simplify(schema.model_json_schema())


class GenerationError(Exception):
    def __init__(self, code: str, message: str, status: int = 502):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass
class ModelResult:
    value: BaseModel
    input_tokens: int | None = None
    output_tokens: int | None = None


class Provider(Protocol):
    name: str
    model: str

    async def generate(self, instructions: str, payload: dict, schema: type[T]) -> ModelResult: ...
    async def close(self) -> None: ...


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str):
        self.model = model
        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=60000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

    async def generate(self, instructions: str, payload: dict, schema: type[T]) -> ModelResult:
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=json.dumps(payload, ensure_ascii=False),
                config=types.GenerateContentConfig(
                    system_instruction=instructions,
                    response_mime_type="application/json",
                    response_json_schema=provider_schema(schema),
                    max_output_tokens=12000,
                ),
            )
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise GenerationError("provider_timeout", "Gemini timed out. Try again.", 504) from exc
        except errors.APIError as exc:
            if exc.code == 504:
                raise GenerationError(
                    "provider_timeout",
                    "Gemini exceeded its response deadline. Try again later.",
                    504,
                ) from exc
            if exc.code == 404:
                raise GenerationError(
                    "provider_model_unavailable",
                    "The configured Gemini model is unavailable. "
                    "Choose an available model in GEMINI_MODEL.",
                ) from exc
            if exc.code == 429:
                raise GenerationError(
                    "provider_rate_limit",
                    "Gemini quota or rate limit reached. Try later.",
                    429,
                ) from exc
            raise GenerationError(
                "provider_error",
                "Gemini request failed. Check your API key and model configuration.",
            ) from exc
        except httpx.RequestError as exc:
            raise GenerationError("provider_unavailable", "Cannot reach Gemini.", 503) from exc

        candidates = response.candidates or []
        if not candidates or candidates[0].finish_reason != types.FinishReason.STOP:
            raise GenerationError(
                "incomplete_output",
                "Gemini blocked or did not finish the output. Try a different request.",
            )
        try:
            value = schema.model_validate_json(response.text or "")
        except ValidationError as exc:
            raise GenerationError(
                "invalid_model_output",
                "Gemini returned output that did not match the expected structure.",
            ) from exc
        usage = response.usage_metadata
        return ModelResult(
            value=value,
            input_tokens=usage.prompt_token_count if usage else None,
            output_tokens=usage.candidates_token_count if usage else None,
        )

    async def close(self) -> None:
        await self.client.aio.aclose()
        self.client.close()


class DemoProvider:
    name = "demo"
    model = "fixed-fixture-v1"

    async def generate(self, instructions: str, payload: dict, schema: type[T]) -> ModelResult:
        if schema is Assessment:
            # Fixed sample scores demonstrate the contract, not quality measurement.
            def rating(score: int, explanation: str, evidence: str) -> DimensionRating:
                return DimensionRating(
                    score=score,
                    explanation=explanation,
                    evidence=evidence,
                    scene_numbers=[1, 2, 3],
                )

            return ModelResult(
                Assessment(
                    narrative_coherence=rating(
                        7,
                        "A simple complete sequence.",
                        "Mira finds a letter, follows the train number, and returns it.",
                    ),
                    character_consistency=rating(
                        8,
                        "Mira keeps her goal throughout.",
                        "All three scenes show Mira trying to return the letter.",
                    ),
                    repetition_avoidance=rating(
                        8,
                        "Each scene moves the sample forward.",
                        "Discovery, pursuit, and return cover different events.",
                    ),
                    language_quality=rating(
                        7,
                        "The fixed English sample is readable.",
                        "Short sentences describe the letter and the train.",
                    ),
                    instruction_adherence=rating(
                        2,
                        "The fixture ignores user preferences.",
                        "The fixed letter story does not adapt to the requested premise or length.",
                    ),
                    summary="Fixed demonstration assessment only, not an LLM judgment.",
                    revision_suggestions=[
                        "Write a story matching the requested premise and language.",
                        "Expand the scenes toward the requested length.",
                    ],
                )
            )
        if schema is Outline:
            outline = Outline(
                title="Demo: The Letter at Dawn",
                setting="A fictional railway station at dawn.",
                conflict="A missing letter must reach its owner before the last train departs.",
                characters=[
                    Character(name="Mira", goal="Return the letter", traits="Curious and honest")
                ],
                scene_beats=[
                    "Mira discovers a misplaced letter.",
                    "She follows a clue to the departing train.",
                    "She returns the letter and resolves the misunderstanding.",
                ],
            )
            return ModelResult(outline)
        if schema is not Script:
            raise ValueError("Unsupported demo output schema")
        outline = Outline.model_validate(payload["outline"])
        script = Script(
            title=outline.title,
            scenes=[
                Scene(
                    heading="Discovery",
                    narration="Mira found a letter beneath the station bench.",
                    dialogue=[Dialogue(speaker="Mira", text="Someone must be waiting for this.")],
                ),
                Scene(
                    heading="The clue",
                    narration="The envelope bore the number of the departing train.",
                    dialogue=[
                        Dialogue(speaker="Mira", text="There is still time to reach the platform.")
                    ],
                ),
                Scene(
                    heading="Return",
                    narration="Mira handed the letter to its owner before the whistle.",
                    dialogue=[
                        Dialogue(
                            speaker="Mira", text="Your message has finally found its way home."
                        )
                    ],
                ),
            ],
        )
        if "previous_script" in payload:
            script.scenes[
                0
            ].narration += (
                " The departure bell rang as she noticed the train number on the envelope."
            )
        return ModelResult(script)

    async def close(self) -> None:
        pass


def create_provider() -> Provider:
    # Explicit path avoids accidentally loading a .env from an unrelated parent project.
    load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)
    name = os.getenv("STORY_PROVIDER", "demo").strip().lower()
    if name == "demo":
        return DemoProvider()
    if name != "gemini":
        raise GenerationError("configuration_error", "STORY_PROVIDER must be demo or gemini.", 503)
    key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "").strip()
    if not key or not model:
        raise GenerationError(
            "configuration_error",
            "Set GEMINI_API_KEY and GEMINI_MODEL in your local .env file.",
            503,
        )
    return GeminiProvider(key, model)
