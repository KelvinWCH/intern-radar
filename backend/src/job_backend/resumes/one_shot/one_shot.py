import json
from collections.abc import Callable
from dataclasses import dataclass

import httpx2
from pydantic import JsonValue, TypeAdapter

from job_backend.common.ai_completion import AiCompletionError, complete_json
from job_backend.common.ai_usage import AiUsageTracker
from job_backend.common.models import AiSettings, AiUsage, CompletionOutput
from job_backend.jobs.models import TailoringJob
from job_backend.profile.models import ResumeSettings, UserProfile
from job_backend.profile.tailoring import tailoring_source
from job_backend.resumes.compile_pdf.models import PdfCompiler
from job_backend.resumes.generate_cover_letter.constants import COVER_LETTER_PROMPT
from job_backend.resumes.generate_resume.generate import resume_writer_prompt
from job_backend.resumes.models import ResearchReport, UserResume
from job_backend.resumes.one_shot.constants import (
    ONE_SHOT_KEY,
    ONE_SHOT_PROMPT,
    ONE_SHOT_STEP_KEYS,
    ONE_SHOT_STEP_ORDER,
    ONE_SHOT_TIMEOUT_SECONDS,
)
from job_backend.resumes.one_shot.models import OneShotOutput, OneShotStep
from job_backend.resumes.research.analyze import collect_sources, keep_verified, validate_research
from job_backend.resumes.research.constants import (
    GENERIC_RESEARCH_PROMPT,
    RESEARCH_PROMPT,
)
from job_backend.resumes.research.generic import generic_research_prompt
from job_backend.resumes.review.constants import REVIEW_PROMPT, REVISION_PROMPT


@dataclass(frozen=True)
class OneShotResult:
    research: ResearchReport
    output: OneShotOutput
    usage: AiUsage


def one_shot_prompt(
    profile: UserResume,
    *,
    generic: bool,
    include_resume: bool,
    include_cover_letter: bool,
    compiler: PdfCompiler | None = None,
) -> str:
    sections = [
        ONE_SHOT_PROMPT,
        "# Research rules\n" + (GENERIC_RESEARCH_PROMPT if generic else RESEARCH_PROMPT),
    ]
    if include_resume:
        minimums = profile.resume_settings if isinstance(profile, UserProfile) else ResumeSettings()
        sections.append(
            "# Resume rules\n"
            + resume_writer_prompt(tailoring_source(profile), minimums, compiler=compiler)
        )
    if include_cover_letter:
        sections.append("# Cover letter rules\n" + COVER_LETTER_PROMPT)
    sections.append("# Review rules\n" + REVIEW_PROMPT)
    sections.append("# Revision rules\n" + REVISION_PROMPT)
    return "\n\n".join(sections)


def run_one_shot(
    job: TailoringJob,
    profile: UserResume,
    settings: AiSettings,
    *,
    include_resume: bool,
    include_cover_letter: bool,
    company_url: str | None = None,
    research_prompt: str | None = None,
    instructions: str | None = None,
    compiler: PdfCompiler | None = None,
    transport: httpx2.BaseTransport | None = None,
    on_output: Callable[[CompletionOutput], None] | None = None,
    on_usage: Callable[[AiUsage], None] | None = None,
    on_completion: Callable[[dict[str, JsonValue]], None] | None = None,
) -> OneShotResult:
    config = settings.model_copy(
        update={"timeout_seconds": max(settings.timeout_seconds, ONE_SHOT_TIMEOUT_SECONDS)}
    )
    usage = AiUsageTracker(config)

    def record_usage(value: AiUsage) -> None:
        usage.record(value)
        if on_usage is not None:
            on_usage(value)

    generic = not job.raw_description.strip()
    sources, warnings = collect_sources(job, config, company_url=company_url)
    if generic:
        sources = [source for source in sources if source.text.strip()]
    focus = (research_prompt or "").strip() or generic_research_prompt(job.company, job.title)
    documents = [
        name
        for name, selected in (("resume", include_resume), ("cover_letter", include_cover_letter))
        if selected
    ]
    payload: dict[str, object] = {
        "documents_to_write": documents,
        "job": job.metadata(),
        "scraped_qualifications": (
            job.qualifications.model_dump(mode="json") if job.qualifications else None
        ),
        "sources": [source.model_dump(mode="json") for source in sources],
        "user_resume": tailoring_source(profile).model_dump(
            mode="json", exclude={"resume_settings"}
        ),
    }
    if generic:
        payload["research_focus"] = focus
    if instructions and instructions.strip():
        payload["candidate_instructions"] = instructions.strip()
    user = json.dumps(payload, ensure_ascii=False)
    if len(user) > config.max_document_chars:
        raise ValueError(
            "Job sources and profile exceed JOB_AI_MAX_DOCUMENT_CHARS; no data was truncated"
        )
    prompt = one_shot_prompt(
        profile,
        generic=generic,
        include_resume=include_resume,
        include_cover_letter=include_cover_letter,
        compiler=compiler,
    )
    output = complete_json(
        config,
        system_prompt=prompt,
        user_content=user,
        response_model=OneShotOutput,
        schema_name="one_shot_application",
        transport=transport,
        on_usage=record_usage,
        on_output=on_output,
        on_report=on_completion,
    )
    missing = [
        name
        for name, selected, final in (
            ("resume", include_resume, output.resume),
            ("cover letter", include_cover_letter, output.cover_letter),
        )
        if selected and final is None
    ]
    if missing:
        raise AiCompletionError(f"The one-shot answer did not include the final {missing[0]}")
    report = ResearchReport(
        analysis=output.research,
        sources=sources,
        warnings=warnings,
        ai_usage=usage.snapshot(),
        mode="generic" if generic else "job_description",
        research_prompt=focus if generic else "",
        system_prompt=GENERIC_RESEARCH_PROMPT if generic else RESEARCH_PROMPT,
        qualifications=job.qualifications,
    )
    keep_verified(report)
    validate_research(report)
    return OneShotResult(research=report, output=output, usage=usage.snapshot())


def one_shot_step(text: str, current: OneShotStep | None) -> OneShotStep | None:
    seen = [ONE_SHOT_STEP_KEYS[key] for key in ONE_SHOT_KEY.findall(text)]
    if current is not None:
        seen.append(current)
    if not seen:
        return None
    furthest = max(seen, key=ONE_SHOT_STEP_ORDER.index)
    return _STEPS.validate_python(furthest)


_STEPS: TypeAdapter[OneShotStep] = TypeAdapter(OneShotStep)
