import httpx2

from job_backend.resumes.models import ResearchAnalysis, ResearchFinding
from job_backend.resumes.research.analyze import analyze_target
from tests.resumes.helpers import (
    completion,
    job,
    settings,
)


def analysis(**changes: object) -> ResearchAnalysis:
    base = ResearchAnalysis(
        mission=None,
        company_context=[],
        role_priorities=[
            ResearchFinding(finding="Python APIs", source_index=0, quote="Build Python APIs")
        ],
        requirements=[],
        keywords=["Python", "Redis"],
        tailoring_guidance=["Lead with API results"],
        unknowns=[],
    )
    return base.model_copy(update=changes)


def test_uncited_findings_dropped() -> None:
    returned = analysis(
        role_priorities=[
            ResearchFinding(finding="Python APIs", source_index=0, quote="build  python APIs."),
            ResearchFinding(finding="Invented duty", source_index=0, quote="Manage a team of 8"),
        ],
        keywords=["Python", "redis", "Redis", "Kubernetes"],
    )
    report = analyze_target(
        job(),
        settings(),
        transport=httpx2.MockTransport(lambda _request: completion(returned.model_dump_json())),
    )
    assert [item.finding for item in report.analysis.role_priorities] == ["Python APIs"]
    assert any("Invented duty" in warning for warning in report.warnings)
    assert report.validated and not report.validation_issues
    assert report.analysis.keywords == ["Python", "Redis"]
