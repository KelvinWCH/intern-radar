import unicodedata

from job_backend.common.ai_completion import AiCompletionError
from job_backend.resumes.models import (
    ApplicationReview,
    ReviewAnalysis,
    ReviewFinding,
)


def _normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _same_scope(finding: ReviewFinding, previous: ReviewFinding) -> bool:
    severities = {"suggestion": 0, "warning": 1, "error": 2}
    return (
        finding.category == previous.category
        and (finding.document == previous.document or previous.document == "both")
        and severities[finding.severity] <= severities[previous.severity]
    )


def acknowledged_findings(
    analysis: ReviewAnalysis, previous_review: ApplicationReview | None, *, round_number: int
) -> list[int]:
    history = {
        (previous.round, index): finding
        for previous in (previous_review.passes if previous_review is not None else [])
        for index, finding in enumerate(previous.analysis.findings)
    }
    for finding in analysis.findings:
        reference = finding.previous_finding
        if reference is not None and (
            reference.round >= round_number
            or (reference.round, reference.finding_index) not in history
        ):
            raise AiCompletionError(
                "Reviewer referenced a finding outside the saved review history"
            )
    if previous_review is None:
        return []
    decided = {
        (decision.round, item.finding_index)
        for decision in previous_review.decisions
        for item in decision.decisions
    }
    if not decided:
        return []

    def earlier_matches(finding: ReviewFinding, before_round: int) -> list[tuple[int, int]]:
        reference = finding.previous_finding
        issue = _normalized(finding.issue).rstrip(".!?")
        return [
            key
            for key, earlier in history.items()
            if key[0] < before_round
            and _same_scope(finding, earlier)
            and (
                (reference is not None and key == (reference.round, reference.finding_index))
                or (
                    bool(issue)
                    and issue == _normalized(earlier.issue).rstrip(".!?")
                    and _normalized(finding.draft_quote) == _normalized(earlier.draft_quote)
                )
            )
        ]

    def was_decided(finding: ReviewFinding) -> bool:
        pending = earlier_matches(finding, round_number)
        visited: set[tuple[int, int]] = set()
        while pending:
            key = pending.pop()
            if key in visited:
                continue
            if key in decided:
                return True
            visited.add(key)
            pending.extend(earlier_matches(history[key], key[0]))
        return False

    return [
        index
        for index, finding in enumerate(analysis.findings)
        if finding.severity != "suggestion" and was_decided(finding)
    ]
