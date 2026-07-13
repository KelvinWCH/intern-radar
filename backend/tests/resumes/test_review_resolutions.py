from typing import Literal

import pytest
from pydantic import JsonValue

from job_backend.common.models import AiUsage
from job_backend.resumes.models import (
    ApplicationReview,
    FindingDecision,
    ReviewAnalysis,
    ReviewDecision,
    ReviewFinding,
    ReviewPass,
)
from job_backend.resumes.review.resolutions import acknowledged_findings


def _finding(**changes: JsonValue) -> ReviewFinding:
    return ReviewFinding.model_validate(
        {
            "document": "resume",
            "category": "requirements",
            "severity": "warning",
            "draft_quote": "Expected April 2028",
            "issue": "The graduation date is earlier than the required date.",
            "recommendation": "Keep the actual date and assess eligibility.",
            **changes,
        }
    )


def _pass(round_number: int, findings: list[ReviewFinding]) -> ReviewPass:
    return ReviewPass(
        round=round_number,
        analysis=ReviewAnalysis(summary="Eligibility review", findings=findings),
        document_hashes={"resume": "a" * 64},
        ai_usage=AiUsage(model_name="test", calls=1),
    )


def _review(action: Literal["keep", "revise"] = "keep") -> ApplicationReview:
    return ApplicationReview(
        passes=[_pass(1, [_finding()])],
        decisions=[
            ReviewDecision(round=1, decisions=[FindingDecision(finding_index=0, action=action)])
        ],
    )


@pytest.mark.parametrize(
    "change", [{"severity": "error"}, {"document": "both"}, {"document": "cover_letter"}]
)
def test_new_issue_needs_decision(change: dict[str, JsonValue]) -> None:
    current = _pass(2, [_finding(**change, previous_finding={"round": 1, "finding_index": 0})])
    assert acknowledged_findings(current.analysis, _review(), round_number=2) == []
