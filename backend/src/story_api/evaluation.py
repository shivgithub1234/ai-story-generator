"""Application-owned scoring; the model cannot choose its own aggregate or threshold."""

from story_api.generation_models import Assessment, EvaluationReport
from story_api.providers import GenerationError

RUBRIC_VERSION = "story-quality-v1"
REVISION_THRESHOLD = 7.0
DIMENSION_THRESHOLD = 4
DIMENSIONS = (
    "narrative_coherence",
    "character_consistency",
    "repetition_avoidance",
    "language_quality",
    "instruction_adherence",
)


def build_report(assessment: Assessment, scene_count: int) -> EvaluationReport:
    ratings = [getattr(assessment, dimension) for dimension in DIMENSIONS]
    if any(number > scene_count for rating in ratings for number in rating.scene_numbers):
        raise GenerationError(
            "invalid_model_output", "Evaluator cited a scene that does not exist in the script."
        )
    average = sum(rating.score for rating in ratings) / len(ratings)
    return EvaluationReport(
        rubric_version=RUBRIC_VERSION,
        assessment=assessment,
        overall_score=round(average, 2),
        revision_threshold=REVISION_THRESHOLD,
        dimension_threshold=DIMENSION_THRESHOLD,
        needs_revision=(
            average < REVISION_THRESHOLD
            or any(rating.score < DIMENSION_THRESHOLD for rating in ratings)
        ),
    )
