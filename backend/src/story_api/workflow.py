"""A two-node LangGraph with explicit shared state and no hidden retry loop."""

from time import perf_counter
from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from story_api.generation_models import GenerationResponse, Outline, Script, StepUsage
from story_api.prompts import PLANNER, PROMPT_VERSION, WRITER
from story_api.providers import GenerationError, Provider
from story_api.schemas import StoryRequest


class StoryState(TypedDict, total=False):
    request: dict
    outline: Outline
    script: Script
    usage: list[StepUsage]


def build_graph(provider: Provider):
    async def planner(state: StoryState) -> dict:
        start = perf_counter()
        result = await provider.generate(PLANNER, {"request": state["request"]}, Outline)
        outline = Outline.model_validate(result.value)
        names = [character.name for character in outline.characters]
        if len(set(names)) != len(names):
            raise GenerationError(
                "invalid_model_output", "Planner returned duplicate character names."
            )
        return {
            "outline": outline,
            "usage": [
                StepUsage(
                    step="planner",
                    elapsed_ms=round((perf_counter() - start) * 1000),
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                )
            ],
        }

    async def writer(state: StoryState) -> dict:
        start = perf_counter()
        outline = state["outline"]
        result = await provider.generate(
            WRITER,
            {
                "request": state["request"],
                "outline": outline.model_dump(),
            },
            Script,
        )
        script = Script.model_validate(result.value)
        names = {character.name for character in outline.characters}
        if (
            script.title != outline.title
            or len(script.scenes) != len(outline.scene_beats)
            or any(line.speaker not in names for scene in script.scenes for line in scene.dialogue)
        ):
            raise GenerationError(
                "invalid_model_output",
                "Writer output did not preserve the outline's title, scenes, or characters.",
            )
        return {
            "script": script,
            "usage": [
                *state["usage"],
                StepUsage(
                    step="writer",
                    elapsed_ms=round((perf_counter() - start) * 1000),
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                ),
            ],
        }

    graph = StateGraph(StoryState)
    graph.add_node("planner", planner)
    graph.add_node("writer", writer)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "writer")
    graph.add_edge("writer", END)
    return graph.compile()


async def generate_story(request: StoryRequest, provider: Provider) -> GenerationResponse:
    state = await build_graph(provider).ainvoke({"request": request.model_dump()})
    script = state["script"]
    sections = [script.title]
    for number, scene in enumerate(script.scenes, 1):
        sections.append(
            f"Scene {number}: {scene.heading}\nNarration: {scene.narration}\n"
            + "\n".join(f"{line.speaker}: {line.text}" for line in scene.dialogue)
        )
    return GenerationResponse(
        run_id=str(uuid4()),
        provider=provider.name,
        model=provider.model,
        is_demo=provider.name == "demo",
        prompt_version=PROMPT_VERSION,
        outline=state["outline"],
        script=script,
        final_text="\n\n".join(sections),
        usage=state["usage"],
        warnings=[
            "Demo fixture only: not AI-generated; ignores premise, language, tone, and length."
        ]
        if provider.name == "demo"
        else ["Unevaluated draft: the judge and feedback-based revision are not implemented yet."],
    )
