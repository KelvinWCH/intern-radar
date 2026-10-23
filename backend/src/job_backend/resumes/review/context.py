from pydantic import JsonValue, TypeAdapter

from job_backend.resumes.models import ApplicationReview, FindingDecision


def review_history(review: ApplicationReview) -> list[dict[str, JsonValue]]:
    json_object = TypeAdapter(dict[str, JsonValue])
    latest_choices: dict[tuple[int, int], FindingDecision] = {
        (decision.round, item.finding_index): item
        for decision in review.decisions
        for item in decision.decisions
    }
    return [
        json_object.validate_python(
            {
                "round": previous.round,
                "summary": previous.analysis.summary,
                "findings": previous.analysis.model_dump(mode="json", exclude_none=True)[
                    "findings"
                ],
                "acknowledged_finding_indices": previous.acknowledged_finding_indices,
                "decisions": [
                    item.model_dump(mode="json")
                    for (round_number, _), item in latest_choices.items()
                    if round_number == previous.round
                ],
            }
        )
        for previous in review.passes
    ]
