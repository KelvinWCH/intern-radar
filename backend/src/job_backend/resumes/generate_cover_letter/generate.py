import json
import re
from collections.abc import Callable

import httpx2
from pydantic import JsonValue, ValidationError

from job_backend.common.ai_completion import AiCompletionError, complete_json
from job_backend.common.ai_usage import AiUsageTracker
from job_backend.common.models import AiSettings, AiUsage, CompletionOutput
from job_backend.jobs.models import Job, JobResponse, TailoringJob
from job_backend.persistence.database import Database
from job_backend.profile.tailoring import tailoring_source
from job_backend.resumes.compile_pdf.models import PdfCompiler
from job_backend.resumes.database import resume_database
from job_backend.resumes.generate_cover_letter.constants import COVER_LETTER_PROMPT
from job_backend.resumes.generate_cover_letter.models import LetterContent
from job_backend.resumes.generation import DraftRevisionRequired, generate_one_page
from job_backend.resumes.models import GeneratedCoverLetter, ProgressCallback, UserResume
from job_backend.resumes.progress import report_progress
from job_backend.resumes.review.constants import REVISION_PROMPT
from job_backend.resumes.storage import load_resume
from job_backend.scrape.pipeline.models import ScrapedJob


def generate_cover_letter(
    job: Job | ScrapedJob | JobResponse | TailoringJob,
    *,
    resume: UserResume | None = None,
    engine: Database | None = None,
    settings: AiSettings | None = None,
    transport: httpx2.BaseTransport | None = None,
    compiler: PdfCompiler | None = None,
    on_output: Callable[[CompletionOutput], None] | None = None,
    on_usage: Callable[[AiUsage], None] | None = None,
    instructions: str | None = None,
    on_progress: ProgressCallback | None = None,
    research: dict[str, JsonValue] | None = None,
    on_report: Callable[[dict[str, JsonValue]], None] | None = None,
    review_revision: dict[str, JsonValue] | None = None,
    on_pdf: Callable[[GeneratedCoverLetter, bytes], None] | None = None,
    revision_feedback: str = "",
    first_draft: LetterContent | None = None,
) -> GeneratedCoverLetter:
    try:
        target = TailoringJob.model_validate(job, from_attributes=True)
    except ValidationError:
        raise ValueError(
            "Cover-letter generation needs a job with a full raw_description"
        ) from None
    if not target.raw_description.strip():
        raise ValueError("Generate a company and role research report before writing documents.")
    if resume is None:
        with resume_database(engine) as database:
            resume = load_resume(database)
    resume = tailoring_source(resume)
    if not any([resume.education, resume.experience, resume.projects, resume.skills]):
        raise ValueError("Cover-letter generation needs usable candidate experience or skills")
    config = settings or AiSettings.from_environment()
    usage = AiUsageTracker(config)

    def record_usage(value: AiUsage) -> None:
        usage.record(value)
        if on_usage is not None:
            on_usage(value)

    payload: dict[str, object] = {
        "job": target.metadata() if research is not None else target.model_dump(mode="json"),
        "user_resume": resume.model_dump(mode="json"),
    }
    if research is not None:
        payload["company_role_research"] = research
    if review_revision is not None:
        payload["review_revision"] = review_revision
    if instructions and instructions.strip():
        payload["candidate_instructions"] = instructions.strip()
    revision_prompt = REVISION_PROMPT if review_revision is not None else ""
    report_progress(on_progress, "prepare", "Preparing saved experience and job description for AI")
    user = json.dumps(payload, ensure_ascii=False)
    if len(user) > config.max_document_chars:
        raise ValueError(
            "Job and user resume exceed JOB_AI_MAX_DOCUMENT_CHARS; no data was truncated"
        )
    source = resume

    supplied = [first_draft] if first_draft is not None else []

    def make_draft(feedback: str) -> GeneratedCoverLetter:
        if supplied:
            content = supplied.pop()
            report_progress(on_progress, "validate", "Draft received, checking the opening")
        else:
            report_progress(on_progress, "ai", "Sent to the model, waiting for the draft")
            content = complete_json(
                config,
                system_prompt=COVER_LETTER_PROMPT + revision_prompt + feedback,
                user_content=user,
                response_model=LetterContent,
                schema_name="cover_letter_content",
                transport=transport,
                on_usage=record_usage,
                on_output=on_output,
                on_report=on_report,
            )
            report_progress(on_progress, "validate", "Model draft received, checking the opening")
        opening = content.paragraphs[0].strip().replace("\u2019", "'")
        if re.match(
            r"(?:i (?:am|'m) (?:applying|writing to apply|excited to apply)|"
            r"i'm (?:applying|writing to apply|excited to apply)|"
            r"please accept my application|i am a perfect fit)\b",
            opening,
            re.IGNORECASE,
        ):
            raise DraftRevisionRequired(
                "The previous opening was an application announcement. Explain a specific "
                "reason this company's work appeals to the candidate and connect it to a "
                "supported goal or capability. Use experience as evidence of fit, not a recap. "
                "Do not start with 'I am applying', 'I am writing to apply', or generic enthusiasm."
            )
        try:
            return GeneratedCoverLetter(
                name=source.name,
                email=source.email,
                phone=source.phone,
                location=source.location,
                linkedin=source.linkedin,
                linkedin_label=source.linkedin_label,
                github=source.github,
                links=source.links.copy(),
                company=target.company,
                job_title=target.title,
                greeting="Dear Hiring Manager,",
                paragraphs=list(content.paragraphs),
                closing="Sincerely,",
            )
        except ValidationError as error:
            raise AiCompletionError(
                "AI output exceeds the cover-letter content constraints"
            ) from error

    result = generate_one_page(
        make_draft,
        compiler=compiler,
        feedback=revision_feedback,
        on_progress=on_progress,
        on_pdf=on_pdf,
    )
    result.ai_usage = usage.snapshot()
    return result
