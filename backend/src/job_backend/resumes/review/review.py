import hashlib
import json
from collections.abc import Callable

import httpx2
from pydantic import JsonValue

from job_backend.common.ai_completion import complete_json
from job_backend.common.ai_usage import AiUsageTracker
from job_backend.common.models import AiSettings, AiUsage, CompletionOutput
from job_backend.jobs.models import TailoringJob
from job_backend.profile.tailoring import tailoring_source
from job_backend.resumes.models import (
    ApplicationReview,
    GeneratedCoverLetter,
    GeneratedResume,
    PdfDiagnostics,
    ResearchReport,
    ReviewAnalysis,
    ReviewFinding,
    ReviewPass,
    UserResume,
)
from job_backend.resumes.review.constants import REVIEW_PROMPT
from job_backend.resumes.review.context import review_history
from job_backend.resumes.review.resolutions import acknowledged_findings
from job_backend.resumes.text_match import quoted_in


def document_hash(document: GeneratedResume | GeneratedCoverLetter) -> str:
    content = json.dumps(
        document.model_dump(mode="json", exclude={"ai_usage"}),
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _strings(value: JsonValue) -> list[str]:
    if isinstance(value, str):
        return [" ".join(value.split())]
    if isinstance(value, list):
        return [text for child in value for text in _strings(child)]
    if isinstance(value, dict):
        return [text for child in value.values() for text in _strings(child)]
    return []


def _research_input(research: ResearchReport) -> dict[str, JsonValue]:
    report: dict[str, JsonValue] = research.model_dump(
        mode="json", exclude={"system_prompt", "ai_usage", "sources"}
    )
    return report


def review_application(
    job: TailoringJob,
    profile: UserResume,
    research: ResearchReport,
    resume: GeneratedResume | None,
    letter: GeneratedCoverLetter | None,
    settings: AiSettings,
    *,
    round_number: int,
    previous_review: ApplicationReview | None = None,
    diagnostics: list[PdfDiagnostics] | None = None,
    transport: httpx2.BaseTransport | None = None,
    on_output: Callable[[CompletionOutput], None] | None = None,
    on_usage: Callable[[AiUsage], None] | None = None,
    on_report: Callable[[dict[str, JsonValue]], None] | None = None,
) -> ReviewPass:
    documents = {
        key: value
        for key, value in {"resume": resume, "cover_letter": letter}.items()
        if value is not None
    }
    if not documents:
        raise ValueError("Application review requires at least one document")
    review_input: dict[str, JsonValue] = {
        "job": job.model_copy(
            update={"raw_description": "", "cleaned_description": None, "qualifications": None}
        ).model_dump(mode="json")
        if research.mode == "generic"
        else job.model_dump(mode="json"),
        "user_resume": tailoring_source(profile).model_dump(mode="json"),
        "company_role_research": _research_input(research),
        "documents": {
            key: value.model_dump(mode="json", exclude={"ai_usage"})
            for key, value in documents.items()
        },
        "round": round_number,
    }
    checks: list[JsonValue] = [
        {
            "document": report.document,
            "matched_required_skills": list(report.matched_required_skills),
            "missing_supported_skills": list(report.missing_supported_skills),
            "unsupported_required_skills": list(report.unsupported_required_skills),
            "matched_keywords": list(report.matched_keywords),
            "missing_supported_keywords": list(report.missing_supported_keywords),
            "unsupported_keywords": list(report.unsupported_keywords),
        }
        for report in diagnostics or []
        if report.document == "resume" and "resume" in documents
    ]
    if checks:
        review_input["pdf_checks"] = checks
    if previous_review is not None and previous_review.passes:
        review_input["review_history"] = list(review_history(previous_review))
    payload = json.dumps(review_input, ensure_ascii=False)
    if len(payload) > settings.max_document_chars:
        raise ValueError(
            "Application review exceeds JOB_AI_MAX_DOCUMENT_CHARS; no data was truncated"
        )
    usage = AiUsageTracker(settings)

    def record_usage(value: AiUsage) -> None:
        usage.record(value)
        if on_usage:
            on_usage(value)

    analysis = complete_json(
        settings,
        system_prompt=REVIEW_PROMPT,
        user_content=payload,
        response_model=ReviewAnalysis,
        schema_name="application_review",
        transport=transport,
        on_usage=record_usage,
        on_output=on_output,
        on_report=on_report,
    )
    texts = {
        key: _strings(value.model_dump(mode="json", exclude={"ai_usage"}))
        for key, value in documents.items()
    }

    def grounded(finding: ReviewFinding) -> bool:
        keys = ["resume", "cover_letter"] if finding.document == "both" else [finding.document]
        if any(key not in texts for key in keys):
            return False
        if finding.document == "cover_letter" and finding.category != "writing":
            return False
        return not finding.draft_quote.strip() or any(
            quoted_in(finding.draft_quote, text) for key in keys for text in texts[key]
        )

    analysis.findings = [finding for finding in analysis.findings if grounded(finding)]
    return ReviewPass(
        round=round_number,
        analysis=analysis,
        document_hashes={key: document_hash(value) for key, value in documents.items()},
        ai_usage=usage.snapshot(),
        acknowledged_finding_indices=acknowledged_findings(
            analysis, previous_review, round_number=round_number
        ),
    )
