import json
from collections.abc import Callable
from urllib.parse import urlsplit

import httpx2
from pydantic import JsonValue

from job_backend.common.ai_completion import AiCompletionError, complete_json
from job_backend.common.ai_usage import AiUsageTracker
from job_backend.common.models import AiSettings, AiUsage, CompletionOutput
from job_backend.jobs.models import TailoringJob
from job_backend.resumes.models import (
    ResearchAnalysis,
    ResearchReport,
    ResearchSource,
    ResearchSourcePlan,
)
from job_backend.resumes.research.analyze import keep_verified, validate_research
from job_backend.resumes.research.constants import (
    GENERIC_RESEARCH_PROMPT,
    SOURCE_PLAN_PROMPT,
)
from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.pipeline.models import JobPageSettings
from job_backend.scrape.utils.constants import IMPORTER_USER_AGENT
from job_backend.scrape.utils.job_page_http import fetch_http_page
from job_backend.scrape.utils.page_text import page_text


def generic_research_prompt(company: str, role: str) -> str:
    return (
        f"Research what a {role} at {company} typically does. Cover the company's work, "
        "typical responsibilities, relevant skills and tools, example projects, and experience "
        "to highlight in an application. Separate verified company facts from general role "
        "expectations and note what is unknown about this specific opening."
    )


def analyze_generic_target(
    job: TailoringJob,
    settings: AiSettings,
    *,
    research_prompt: str | None = None,
    company_url: str | None = None,
    revision: int = 1,
    transport: httpx2.BaseTransport | None = None,
    on_output: Callable[[CompletionOutput], None] | None = None,
    on_usage: Callable[[AiUsage], None] | None = None,
    on_report: Callable[[ResearchReport], None] | None = None,
    on_completion: Callable[[dict[str, JsonValue]], None] | None = None,
) -> ResearchReport:
    focus = (research_prompt or "").strip() or generic_research_prompt(job.company, job.title)
    metadata = {"company": job.company, "role": job.title, "research_focus": focus}
    source_input = json.dumps(metadata, ensure_ascii=False)
    if len(source_input) > settings.max_document_chars:
        raise ValueError("Research instructions exceed JOB_AI_MAX_DOCUMENT_CHARS")
    usage = AiUsageTracker(settings)

    def record_usage(value: AiUsage) -> None:
        usage.record(value)
        if on_usage:
            on_usage(value)

    warnings = [
        "Generic report: typical role guidance is AI-generated, not verified requirements "
        "for this opening. The original job description was not used."
    ]
    urls = [url] if (url := company_url or job.company_url) else []
    try:
        plan = complete_json(
            settings,
            system_prompt=SOURCE_PLAN_PROMPT,
            user_content=source_input,
            response_model=ResearchSourcePlan,
            schema_name="company_role_source_plan",
            transport=transport,
            on_usage=record_usage,
            on_output=on_output,
            on_report=on_completion,
        )
        urls.extend(plan.urls)
    except AiCompletionError:
        warnings.append("Source planning was unavailable; using any supplied company page.")

    sources: list[ResearchSource] = []
    page_settings = JobPageSettings(timeout_seconds=15, max_page_bytes=500000)
    with httpx2.Client(
        timeout=15,
        follow_redirects=False,
        trust_env=False,
        headers={"User-Agent": IMPORTER_USER_AGENT},
    ) as client:
        for url in list(dict.fromkeys(urls))[:3]:
            try:
                parts = urlsplit(url)
                if parts.query or parts.fragment:
                    raise ValueError("Use plain source URLs")
                page = fetch_http_page(url, client=client, settings=page_settings)
                content = (
                    page_text(page.content, base_url=page.source_url)
                    if "html" in page.media_type
                    else page.content
                )
                source = ResearchSource(
                    title="Public company / role source", url=page.source_url, text=content
                )
                proposed = json.dumps(
                    {
                        **metadata,
                        "sources": [item.model_dump(mode="json") for item in [*sources, source]],
                    },
                    ensure_ascii=False,
                )
                if len(proposed) > settings.max_document_chars:
                    warnings.append(f"Source exceeds the research input budget: {url}")
                    continue
                sources.append(source)
            except (SourceDataError, ValueError):
                warnings.append(f"Could not read research source: {url}")
    if not sources:
        warnings.append(
            "No public pages could be read. This report contains general role guidance."
        )
    user_content = json.dumps(
        {**metadata, "sources": [source.model_dump(mode="json") for source in sources]},
        ensure_ascii=False,
    )
    if len(user_content) > settings.max_document_chars:
        raise ValueError("Research sources exceed JOB_AI_MAX_DOCUMENT_CHARS")
    analysis = complete_json(
        settings,
        system_prompt=GENERIC_RESEARCH_PROMPT,
        user_content=user_content,
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
        mode="generic",
        research_prompt=focus,
        system_prompt=GENERIC_RESEARCH_PROMPT,
        revision=revision,
    )
    keep_verified(report)
    validate_research(report)
    if on_report:
        on_report(report)
    return report
