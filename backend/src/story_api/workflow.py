"""A bounded graph: plan, write, judge, optionally revise once and judge again."""

from time import perf_counter
from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from story_api.evaluation import build_report
from story_api.generation_models import (
    Assessment,
    EvaluationReport,
    GenerationResponse,
    Outline,
    Script,
    StepUsage,
)
from story_api.prompts import (
    EVALUATOR,
    PLANNER,
    PROMPT_VERSION,
    REVISION,
    REVISION_PROMPT_VERSION,
    WRITER,
)
from story_api.providers import GenerationError, Provider
from story_api.schemas import StoryRequest


class StoryState(TypedDict, total=False):
    request: dict
    outline: Outline
    script: Script
    evaluation: EvaluationReport
    initial_script: Script
    initial_evaluation: EvaluationReport
    revision_count: int
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

    async def write_script(state: StoryState, *, revising: bool = False) -> dict:
        start = perf_counter()
        outline = state["outline"]
        payload = {"request": state["request"], "outline": outline.model_dump()}
        if revising:
            payload.update(
                {
                    "previous_script": state["script"].model_dump(),
                    "feedback": state["evaluation"].model_dump(),
                }
            )
        result = await provider.generate(REVISION if revising else WRITER, payload, Script)
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
            "revision_count": 1 if revising else 0,
            "usage": [
                *state["usage"],
                StepUsage(
                    step="revision" if revising else "writer",
                    elapsed_ms=round((perf_counter() - start) * 1000),
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                ),
            ],
        }

    async def writer(state: StoryState) -> dict:
        return await write_script(state)

    async def revise(state: StoryState) -> dict:
        return await write_script(state, revising=True)

    async def evaluator(state: StoryState) -> dict:
        start = perf_counter()
        result = await provider.generate(
            EVALUATOR,
            {
                "request": state["request"],
                "outline": state["outline"].model_dump(),
                "script": state["script"].model_dump(),
            },
            Assessment,
        )
        assessment = Assessment.model_validate(result.value)
        report = build_report(assessment, len(state["script"].scenes))
        updates = {
            "evaluation": report,
            "usage": [
                *state["usage"],
                StepUsage(
                    step="final_evaluator" if state["revision_count"] else "evaluator",
                    elapsed_ms=round((perf_counter() - start) * 1000),
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                ),
            ],
        }

        if not state["revision_count"]:
            updates.update(
                {
                    "initial_script": state["script"].model_copy(deep=True),
                    "initial_evaluation": report.model_copy(deep=True),
                }
            )
        return updates

    def next_step(state: StoryState) -> str:
        return "revision" if state["evaluation"].needs_revision else END

    graph = StateGraph(StoryState)
    graph.add_node("planner", planner)
    graph.add_node("writer", writer)
    graph.add_node("evaluator", evaluator)
    graph.add_node("revision", revise)
    graph.add_node("final_evaluator", evaluator)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "writer")
    graph.add_edge("writer", "evaluator")
    graph.add_conditional_edges("evaluator", next_step, {"revision": "revision", END: END})
    graph.add_edge("revision", "final_evaluator")
    # No edge back to revision: even a failed final score must stop here.
    graph.add_edge("final_evaluator", END)
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
        revision_prompt_version=REVISION_PROMPT_VERSION,
        outline=state["outline"],
        script=script,
        evaluation=state["evaluation"],
        initial_script=state["initial_script"],
        initial_evaluation=state["initial_evaluation"],
        revision_count=state["revision_count"],
        stop_reason="revision_limit_reached"
        if state["evaluation"].needs_revision
        else "quality_passed",
        final_text="\n\n".join(sections),
        usage=state["usage"],
        warnings=["Demo fixture only: not AI-generated; story and scores are fixed sample data."]
        if provider.name == "demo"
        else ["LLM scores are subjective estimates; a revision may not improve quality."]
        + (
            ["The final draft still needs revision; the one-rewrite limit was reached."]
            if state["evaluation"].needs_revision
            else []
        ),
    )
