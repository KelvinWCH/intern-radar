import json
import re
from collections.abc import Callable
from urllib.parse import urlsplit

import httpx2
from pydantic import JsonValue

from job_backend.common.ai_completion import AiCompletionError, complete_json
from job_backend.common.ai_usage import AiUsageTracker
from job_backend.common.models import AiSettings, AiUsage, CompletionOutput
from job_backend.jobs.models import TailoringJob
from job_backend.profile.required_skills import matches_term
from job_backend.resumes.models import (
    MAX_KEYWORDS,
    ResearchAnalysis,
    ResearchFinding,
    ResearchReport,
    ResearchSource,
    ResearchSourcePlan,
)
from job_backend.resumes.research.constants import RESEARCH_PROMPT, SOURCE_PLAN_PROMPT
from job_backend.resumes.text_match import quoted_in
from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.pipeline.models import JobPageSettings
from job_backend.scrape.utils.constants import IMPORTER_USER_AGENT
from job_backend.scrape.utils.job_page_http import fetch_http_page
from job_backend.scrape.utils.page_text import page_text


def analyze_target(
    job: TailoringJob,
    settings: AiSettings,
    *,
    company_url: str | None = None,
    transport: httpx2.BaseTransport | None = None,
    on_output: Callable[[CompletionOutput], None] | None = None,
    on_usage: Callable[[AiUsage], None] | None = None,
    on_report: Callable[[ResearchReport], None] | None = None,
    on_completion: Callable[[dict[str, JsonValue]], None] | None = None,
) -> ResearchReport:
    usage = AiUsageTracker(settings)

    def record_usage(value: AiUsage) -> None:
        usage.record(value)
        if on_usage:
            on_usage(value)

    def suggest(warnings: list[str]) -> list[str]:
        return _suggest_company_pages(
            job,
            settings,
            transport=transport,
            on_usage=record_usage,
            on_output=on_output,
            on_completion=on_completion,
            warnings=warnings,
        )

    sources, warnings = collect_sources(
        job, settings, company_url=company_url, suggest_pages=suggest
    )
    user = json.dumps(
        {
            "company": job.company,
            "role": job.title,
            "scraped_qualifications": (
                job.qualifications.model_dump(mode="json") if job.qualifications else None
            ),
            "sources": [source.model_dump(mode="json") for source in sources],
        },
        ensure_ascii=False,
    )
    if len(user) > settings.max_document_chars:
        raise ValueError("Research sources exceed JOB_AI_MAX_DOCUMENT_CHARS; no data was truncated")
    analysis = complete_json(
        settings,
        system_prompt=RESEARCH_PROMPT,
        user_content=user,
        response_model=ResearchAnalysis,
        schema_name="company_role_research",
        transport=transport,
        on_usage=record_usage,
        on_output=on_output,
        on_report=on_completion,
    )
    report = ResearchReport(
        analysis=analysis,
        sources=sources,
        warnings=warnings,
        ai_usage=usage.snapshot(),
        system_prompt=RESEARCH_PROMPT,
        qualifications=job.qualifications,
    )
    if on_report:
        on_report(report)
    keep_verified(report)
    validate_research(report)
    if on_report:
        on_report(report)
    return report


def collect_sources(
    job: TailoringJob,
    settings: AiSettings,
    *,
    company_url: str | None = None,
    suggest_pages: Callable[[list[str]], list[str]] | None = None,
) -> tuple[list[ResearchSource], list[str]]:
    sources = [
        ResearchSource(
            title=f"{job.company} · {job.title}", url=job.application_url, text=job.raw_description
        )
    ]
    warnings: list[str] = []
    saved = company_url or job.company_url
    pending = [saved] if saved else suggest_pages(warnings) if suggest_pages is not None else []
    if pending:
        page_settings = JobPageSettings(
            timeout_seconds=15, max_page_bytes=500000, include_links=True
        )
        with httpx2.Client(
            timeout=15,
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": IMPORTER_USER_AGENT},
        ) as client:
            for index in range(2 if saved else 3):
                if index >= len(pending) or len(sources) > 2:
                    break
                try:
                    page = fetch_http_page(pending[index], client=client, settings=page_settings)
                    source_text = (
                        page_text(page.content, base_url=page.source_url)
                        if "html" in page.media_type
                        else page.content
                    )
                    if not saved and job.company.casefold() not in source_text.casefold():
                        warnings.append(
                            f"Skipped a suggested page that does not mention {job.company}: "
                            f"{pending[index]}"
                        )
                        continue
                    if (
                        sum(len(source.text) for source in sources) + len(source_text)
                        > settings.max_document_chars // 2
                    ):
                        warnings.append(
                            f"Company page too large for this research budget: {pending[index]}"
                        )
                        continue
                    sources.append(
                        ResearchSource(
                            title="Company website" if saved else "Company website (found)",
                            url=page.source_url,
                            text=source_text,
                        )
                    )
                    if len(sources) == 2:
                        links: list[str] = re.findall(
                            r"^Link: (https?://\S+)", source_text, re.MULTILINE
                        )
                        about = next(
                            (
                                link
                                for link in links
                                if urlsplit(link).hostname == urlsplit(page.source_url).hostname
                                and re.search(
                                    r"/(about|mission|company)(?:[/-]|$)", urlsplit(link).path
                                )
                                and link != page.source_url
                            ),
                            None,
                        )
                        if about and about not in pending:
                            pending.insert(index + 1, about)
                except (SourceDataError, ValueError):
                    warnings.append(
                        f"Could not read company source: {pending[index]}. "
                        "Research uses the other saved sources."
                    )
    if not saved:
        warnings.append(
            "No company website was saved, so research looked one up from the company's name."
            if len(sources) > 1
            else "No company website was saved or found. Company research uses the job "
            "description and the model's own knowledge of the company."
        )
    return sources, warnings


def _suggest_company_pages(
    job: TailoringJob,
    settings: AiSettings,
    *,
    transport: httpx2.BaseTransport | None,
    on_usage: Callable[[AiUsage], None],
    on_output: Callable[[CompletionOutput], None] | None,
    on_completion: Callable[[dict[str, JsonValue]], None] | None,
    warnings: list[str],
) -> list[str]:
    metadata = {
        "company": job.company,
        "role": job.title,
        "research_focus": "Find the company's official website: its home, about, mission, or "
        "product pages.",
    }
    try:
        plan = complete_json(
            settings,
            system_prompt=SOURCE_PLAN_PROMPT,
            user_content=json.dumps(metadata, ensure_ascii=False),
            response_model=ResearchSourcePlan,
            schema_name="company_role_source_plan",
            transport=transport,
            on_usage=on_usage,
            on_output=on_output,
            on_report=on_completion,
        )
    except AiCompletionError:
        warnings.append("Could not look up the company website; research uses the posting.")
        return []
    return [
        url
        for url in dict.fromkeys(plan.urls)
        if not urlsplit(url).query and not urlsplit(url).fragment
    ]


def _cited(report: ResearchReport, finding: ResearchFinding) -> bool:
    return finding.source_index < len(report.sources) and quoted_in(
        finding.quote, report.sources[finding.source_index].text
    )


def keep_verified(report: ResearchReport) -> None:
    analysis = report.analysis
    dropped: list[ResearchFinding] = []
    if analysis.mission is not None and not _cited(report, analysis.mission):
        dropped.append(analysis.mission)
        analysis.mission = None
    for name in ("company_context", "role_priorities", "requirements", "preferred_qualifications"):
        findings: list[ResearchFinding] = getattr(analysis, name)
        dropped += [finding for finding in findings if not _cited(report, finding)]
        setattr(analysis, name, [finding for finding in findings if _cited(report, finding)])
    report.warnings += [
        f"Removed a finding whose quote was not found in its source: {finding.finding}"
        for finding in dropped
    ]
    if report.mode != "generic" and report.sources:
        posting = report.sources[0].text
        scraped = report.qualifications
        terms = [
            *(scraped.required_skills if scraped else []),
            *analysis.keywords,
            *(scraped.tech_stack + scraped.preferred_skills if scraped else []),
        ]
        unique: dict[str, str] = {}
        for term in (term.strip() for term in terms):
            key = term.casefold()
            if key not in unique or (term in posting and unique[key] not in posting):
                unique[key] = term
        analysis.keywords = [
            term for key, term in unique.items() if key and matches_term(term, posting)
        ][:MAX_KEYWORDS]


def validate_research(report: ResearchReport) -> None:
    findings = [
        (f"{label} {index + 1}", finding)
        for label, items in (
            ("Company context", report.analysis.company_context),
            ("Role priority", report.analysis.role_priorities),
            ("Requirement", report.analysis.requirements),
            ("Preferred qualification", report.analysis.preferred_qualifications),
        )
        for index, finding in enumerate(items)
    ]
    if report.analysis.mission:
        findings.insert(0, ("Company mission", report.analysis.mission))
    issues: list[str] = []
    for label, finding in findings:
        if finding.source_index >= len(report.sources):
            issues.append(f"{label}: the cited source does not exist.")
        elif not finding.quote.strip():
            issues.append(f"{label}: no supporting quote was supplied.")
        elif not quoted_in(finding.quote, report.sources[finding.source_index].text):
            issues.append(f"{label}: the quote was not found in source {finding.source_index + 1}.")
    if report.mode == "generic":
        if not any(item.strip() for item in report.analysis.general_role_guidance):
            issues.append(
                "The generic report did not include useful role guidance. Generate it again."
            )
    elif not findings:
        issues.append("No cited findings were supplied to verify this report.")
    elif not (
        report.analysis.role_priorities
        or report.analysis.requirements
        or report.analysis.preferred_qualifications
    ):
        issues.append(
            "The job description does not supply enough role details. Generate a generic report."
        )
    report.validation_issues = issues
    report.validated = not issues
