import hashlib
import json
import re
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from functools import partial
from threading import RLock
from typing import Literal

import httpx2
from pydantic import BaseModel, JsonValue, TypeAdapter

from job_backend.activity.models import ActivityData
from job_backend.activity.storage import record_activity
from job_backend.common.ai_completion import AiCompletionError
from job_backend.common.ai_usage import AiUsageTracker
from job_backend.common.models import AiModelOptions, AiSettings, CompletionOutput
from job_backend.jobs.application_review import review_documents
from job_backend.jobs.descriptions import description_for_tailoring
from job_backend.jobs.document_response import document_response
from job_backend.jobs.models import (
    DocumentDetail,
    Job,
    JobDocument,
    JobUserRecord,
    PreparedTailoring,
    TailoringJob,
    TailoringProcess,
    TailorRequest,
)
from job_backend.jobs.tailoring_control import (
    pause_expired,
    register_run,
    release_run,
    stop_expired_pause,
    wait_while_paused,
)
from job_backend.jobs.user_service import EditConflictError, JobNotFoundError
from job_backend.persistence.database import Database
from job_backend.persistence.errors import ConflictError
from job_backend.persistence.models import Filter, Order, ReadQuery, record_adapter
from job_backend.persistence.session import Session
from job_backend.profile.tailoring import tailoring_source
from job_backend.resumes.compile_pdf.compile import DocumentLayoutError, PdfCompilerError
from job_backend.resumes.compile_pdf.diagnostics import diagnose_pdf
from job_backend.resumes.generate_cover_letter.generate import generate_cover_letter
from job_backend.resumes.generate_cover_letter.models import LetterContent
from job_backend.resumes.generate_resume.fix_bullets import fix_flagged_bullets
from job_backend.resumes.generate_resume.generate import generate_resume
from job_backend.resumes.generate_resume.models import TailoredContent
from job_backend.resumes.generation import DraftsDidNotFit
from job_backend.resumes.models import (
    ApplicationReview,
    GeneratedCoverLetter,
    GeneratedResume,
    GenerationStage,
    PdfDiagnosticCheck,
    PdfDiagnostics,
    ResearchReport,
    ReviewPass,
    TailoringEvent,
)
from job_backend.resumes.one_shot.constants import ONE_SHOT_STEP_MESSAGES
from job_backend.resumes.one_shot.models import OneShotStep
from job_backend.resumes.one_shot.one_shot import OneShotResult, one_shot_step, run_one_shot
from job_backend.resumes.profile.service import read_profile
from job_backend.resumes.research.analyze import analyze_target
from job_backend.resumes.research.generic import analyze_generic_target
from job_backend.resumes.storage import ResumeNotFoundError
from job_backend.scrape.pipeline.models import Qualifications


def prepare_tailoring(
    engine: Database, job_id: str, request: TailorRequest, settings: AiSettings
) -> PreparedTailoring | DocumentDetail:
    now = int(time.time())
    if request.mode == "one_shot":
        one_shot = request.one_shot_ai_options or AiModelOptions()
        request = request.model_copy(
            update={
                "one_shot_ai_options": one_shot,
                "ai_options": one_shot,
                "research_ai_options": one_shot,
                "resume_ai_options": one_shot,
                "cover_letter_ai_options": one_shot,
                "reviewer_ai_options": one_shot,
            }
        )
    settings = request.ai_options.apply(settings)
    usage = AiUsageTracker(settings)
    json_object = TypeAdapter(dict[str, JsonValue])
    with Session(engine) as session:
        existing = session.get(JobDocument, request.request_id)
        if existing:
            if existing.job_id == job_id:
                return document_response(session, existing, DocumentDetail)
            raise EditConflictError(
                "This tailoring request already exists. Refresh its history before retrying."
            )
        job = session.get(Job, job_id, hydrate=False)
        if job is None:
            raise JobNotFoundError("Job not found")
        target = TailoringJob(
            company=job.company,
            title=job.title,
            raw_description=description_for_tailoring(
                job.raw_description, job.cleaned_description, allow_empty=True
            ),
            application_url=job.application_url,
            company_url=job.company_url,
            qualifications=(
                Qualifications.model_validate(job.qualifications) if job.qualifications else None
            ),
        )
    profile = read_profile(engine)
    if profile.resume is None:
        raise ResumeNotFoundError("Save a source resume before tailoring")
    try:
        with Session(engine) as session, session.begin():
            if session.get(JobDocument, request.request_id) is not None:
                raise EditConflictError(
                    "This tailoring request already exists. Refresh its history."
                )
            user = session.get(JobUserRecord, job_id)
            if user is None:
                user = JobUserRecord(job_id=job_id, updated_at=now)
                session.add(user)
            running = session.find(JobDocument, equal={"job_id": job_id, "status": "running"})
            for previous in running:
                if not _expired(previous):
                    raise EditConflictError("Tailoring is already running for this job.")
                if previous.paused_at is not None:
                    stop_expired_pause(session, previous)
                    continue
                previous.status = "failed"
                previous.finished_at = now
                previous.error = "Tailoring was interrupted before completion."
                _stop_stages(previous, previous.error)
            user.active_document_id = request.request_id
            document = JobDocument(
                id=request.request_id,
                job_id=job_id,
                company=target.company,
                title=target.title,
                job_description=target.raw_description,
                profile_revision=profile.revision,
                status="running",
                created_at=now,
                started_at=now,
                request_snapshot=json_object.validate_python(request.model_dump(mode="json")),
                target_snapshot=json_object.validate_python(target.model_dump(mode="json")),
                has_resume=False,
                has_cover_letter=False,
                ai_options=json_object.validate_python(
                    AiModelOptions.from_settings(settings).model_dump(mode="json")
                ),
                ai_usage=json_object.validate_python(usage.snapshot().model_dump(mode="json")),
                research_ai_options=json_object.validate_python(
                    AiModelOptions.from_settings(
                        request.research_ai_options.apply(settings)
                    ).model_dump(mode="json")
                ),
                resume_ai_options=json_object.validate_python(
                    AiModelOptions.from_settings(
                        (request.resume_ai_options or request.ai_options).apply(settings)
                    ).model_dump(mode="json")
                ),
                cover_letter_ai_options=json_object.validate_python(
                    AiModelOptions.from_settings(
                        (request.cover_letter_ai_options or request.ai_options).apply(settings)
                    ).model_dump(mode="json")
                ),
                profile_snapshot=json_object.validate_python(
                    profile.resume.model_dump(mode="json")
                ),
                reviewer_ai_options=json_object.validate_python(
                    AiModelOptions.from_settings(
                        (request.reviewer_ai_options or request.ai_options).apply(settings)
                    ).model_dump(mode="json")
                ),
                stages=[
                    {
                        "key": "research",
                        "label": "Company & role research",
                        "model": request.research_ai_options.apply(settings).model,
                        "status": "queued",
                        "message": "Waiting to analyze sources",
                    },
                    {
                        "key": "resume",
                        "label": "Resume",
                        "model": (request.resume_ai_options or request.ai_options)
                        .apply(settings)
                        .model,
                        "status": "queued" if request.include_resume else "skipped",
                        "message": "Waiting for research"
                        if request.include_resume
                        else "Not selected",
                    },
                    {
                        "key": "cover_letter",
                        "label": "Cover letter",
                        "model": (request.cover_letter_ai_options or request.ai_options)
                        .apply(settings)
                        .model,
                        "status": "queued" if request.include_cover_letter else "skipped",
                        "message": "Waiting for research"
                        if request.include_cover_letter
                        else "Not selected",
                    },
                    {
                        "key": "pdf_diagnostics",
                        "label": "PDF diagnostics",
                        "model": "Local checks",
                        "status": "queued",
                        "message": "Waiting for compiled documents",
                    },
                    {
                        "key": "reviewer",
                        "label": "Independent reviewer",
                        "model": (request.reviewer_ai_options or request.ai_options)
                        .apply(settings)
                        .model,
                        "status": "queued",
                        "message": "Waiting for rendered drafts",
                    },
                ],
                events=[
                    _event(
                        1,
                        "queued",
                        "One-shot tailoring accepted · one call researches, drafts, reviews "
                        "and revises"
                        if request.mode == "one_shot"
                        else "Tailoring job accepted · waiting to start",
                    )
                ],
            )
            if request.mode == "one_shot":
                for item in document.stages:
                    if item.get("status") == "queued" and item.get("key") != "pdf_diagnostics":
                        item["message"] = "Waiting for the one-shot call"
            session.add(document)
            session.flush()
            snapshot = document_response(session, document, DocumentDetail)
    except ConflictError:
        raise EditConflictError(
            "Tailoring is already running for this job. Refresh its document history."
        ) from None
    return PreparedTailoring(request, settings, target, profile.resume, profile.revision, snapshot)


def tailor_job(
    engine: Database,
    job_id: str,
    request: TailorRequest,
    settings: AiSettings,
    *,
    transport: httpx2.BaseTransport | None = None,
) -> DocumentDetail:
    prepared = prepare_tailoring(engine, job_id, request, settings)
    if isinstance(prepared, DocumentDetail):
        if prepared.status != "completed":
            raise EditConflictError("This tailoring request already exists. Refresh its history.")
        return prepared
    return run_tailoring(engine, prepared, transport=transport)


def _event(
    identifier: int, stage: GenerationStage, message: str, *, details: str | None = None
) -> dict[str, JsonValue]:
    return TypeAdapter(dict[str, JsonValue]).validate_python(
        TailoringEvent(
            id=identifier,
            created_at=int(time.time()),
            stage=stage,
            message=message,
            details=details,
        ).model_dump(mode="json")
    )


def _stop_stages(document: JobDocument, message: str) -> None:
    if document.review is not None and document.review.get("status") in {"reviewing", "revising"}:
        document.review["status"] = "failed"
    for stage in document.stages:
        if stage.get("status") in {"running", "queued"}:
            stage.update(
                status="failed" if stage.get("status") == "running" else "skipped",
                message=message,
            )


def _failure_message(error: Exception) -> str:
    if isinstance(error, AiCompletionError):
        return str(error)
    if isinstance(error, PdfCompilerError):
        return "PDF compilation failed. Check the saved compiler details before retrying."
    if isinstance(error, ValueError):
        return str(error)
    return "Generation was interrupted. Open technical details for the failed stage."


def tailoring_posting(target: TailoringJob, research: ResearchReport) -> TailoringJob:
    if research.mode != "generic":
        return target.model_copy()
    return target.model_copy(
        update={
            "raw_description": "No usable job description. Use the generic company and role "
            "report; typical expectations are not confirmed requirements for this opening.",
            "qualifications": None,
            "cleaned_description": None,
        }
    )


def run_tailoring(
    engine: Database,
    prepared: PreparedTailoring,
    *,
    transport: httpx2.BaseTransport | None = None,
) -> DocumentDetail:
    request, settings, target = prepared.request, prepared.settings, prepared.target
    job_id = prepared.document.job_id
    json_object = TypeAdapter(dict[str, JsonValue])
    usage = AiUsageTracker(settings)
    saved_research = prepared.document.research
    if saved_research is not None and prepared.document.ai_usage is not None:
        usage.record(prepared.document.ai_usage)
    write_lock = RLock()
    output_events: dict[str, int] = {}

    def save_output(key: str, output: CompletionOutput) -> None:
        with write_lock, Session(engine) as session, session.begin():
            row = session.get(JobDocument, request.request_id)
            if row is None or row.status != "running":
                raise EditConflictError("This tailoring attempt is no longer running.")
            event_id = output_events.get(output.request_id)
            if event_id is None:
                event_id = len(row.events) + 1
                output_events[output.request_id] = event_id
                row.events.append(
                    _event(event_id, "output", f"{key.replace('_', ' ').title()} · AI draft output")
                )
            event = row.events[event_id - 1]
            event["output"] = output.text
            if output.reasoning:
                event["reasoning"] = output.reasoning
            if output.schema_name:
                event["output_schema"] = output.schema_name

    one_shot_progress: list[OneShotStep] = []

    def save_one_shot_output(output: CompletionOutput) -> None:
        current = one_shot_progress[-1] if one_shot_progress else None
        step = one_shot_step(output.text, current)
        if step is not None and step != current:
            one_shot_progress.append(step)
            message = ONE_SHOT_STEP_MESSAGES[step]
            with write_lock, Session(engine) as session, session.begin():
                row = session.get(JobDocument, request.request_id)
                if row is None or row.status != "running":
                    raise EditConflictError("This tailoring attempt is no longer running.")
                row.one_shot_step = step
                for item in row.stages:
                    if item.get("key") == "research":
                        item["message"] = message
                row.events.append(_event(len(row.events) + 1, "ai", f"Research · {message}"))
        save_output("one_shot", output)

    def usage_snapshot() -> dict[str, JsonValue]:
        snapshot = usage.snapshot().model_copy(update={"model_name": "Multiple stages"})
        return json_object.validate_python(snapshot.model_dump(mode="json"))

    def stage_progress(
        key: str,
        stage: GenerationStage,
        message: str,
        status: str = "running",
        *,
        details: str | None = None,
    ) -> None:
        if status == "running":
            wait_while_paused(engine, request.request_id, key.replace("_", " ").title())
        with write_lock, Session(engine) as session, session.begin():
            row = session.get(JobDocument, request.request_id)
            if row is None or row.status != "running":
                raise EditConflictError("This tailoring attempt is no longer running.")
            for item in row.stages:
                if item.get("key") == key:
                    item.update(status=status, message=message)
            row.events.append(
                _event(
                    len(row.events) + 1,
                    stage,
                    f"{key.replace('_', ' ').title()} · {message}",
                    details=details,
                )
            )
            row.ai_usage = usage_snapshot()

    def resume_progress(stage: GenerationStage, message: str) -> None:
        stage_progress("resume", stage, message)

    def letter_progress(stage: GenerationStage, message: str) -> None:
        stage_progress("cover_letter", stage, message)

    def save_report(
        stage: Literal["research", "resume", "cover_letter", "reviewer"],
        content: dict[str, JsonValue],
    ) -> None:
        with write_lock, Session(engine) as session, session.begin():
            row = session.get(JobDocument, request.request_id)
            if row is None or row.status != "running":
                raise EditConflictError("This tailoring attempt is no longer running.")
            attempt = sum(item.get("stage") == stage for item in row.reports) + 1
            row.reports.append(
                {
                    "stage": stage,
                    "attempt": attempt,
                    "created_at": int(time.time()),
                    "content": content,
                }
            )

    def resume_report(content: dict[str, JsonValue]) -> None:
        save_report("resume", content)

    def letter_report(content: dict[str, JsonValue]) -> None:
        save_report("cover_letter", content)

    def research_completion(content: dict[str, JsonValue]) -> None:
        save_report("research", content)

    def save_research(report: ResearchReport) -> None:
        with write_lock, Session(engine) as session, session.begin():
            row = session.get(JobDocument, request.request_id)
            if row is None or row.status != "running":
                raise EditConflictError("This tailoring attempt is no longer running.")
            row.research = json_object.validate_python(report.model_dump(mode="json"))

    def save_unfitted(error: Exception) -> None:
        if not isinstance(error, DraftsDidNotFit):
            return
        unfitted = json_object.validate_python(
            {
                "document": error.draft.model_dump(mode="json"),
                "overflow_lines": error.overflow_lines,
            }
        )
        with suppress(Exception), write_lock, Session(engine) as session, session.begin():
            row = session.get(JobDocument, request.request_id)
            if row is not None:
                if isinstance(error.draft, GeneratedResume):
                    row.unfitted_resume = unfitted
                else:
                    row.unfitted_cover_letter = unfitted

    def keep_previous(
        key: Literal["resume", "cover_letter"], error: Exception
    ) -> dict[str, JsonValue] | None:
        if not isinstance(error, DocumentLayoutError):
            return None
        with Session(engine) as session:
            row = session.get(JobDocument, request.request_id)
            previous = None if row is None else row.resume if key == "resume" else row.cover_letter
        if previous is None:
            return None
        stage_progress(
            key,
            "validate",
            "Revision did not fit one page · kept the earlier one-page draft",
            "completed",
            details="".join(traceback.format_exception(error)),
        )
        return previous

    register_run(request.request_id, write_lock)
    one_shot: OneShotResult | None = None
    try:
        if request.mode == "one_shot":
            stage_progress(
                "research", "ai", "One call is researching, drafting, reviewing and revising"
            )
            one_shot = run_one_shot(
                target,
                prepared.resume,
                request.research_ai_options.apply(settings),
                include_resume=request.include_resume,
                include_cover_letter=request.include_cover_letter,
                company_url=request.company_research_url,
                research_prompt=request.research_prompt,
                instructions=request.instructions,
                transport=transport,
                on_usage=usage.record,
                on_output=save_one_shot_output,
                on_completion=research_completion,
            )
            research = one_shot.research
            save_research(research)
            steps: list[
                tuple[Literal["resume", "cover_letter", "reviewer"], str, BaseModel | None]
            ] = [
                ("resume", "One-shot first draft", one_shot.output.resume_draft),
                ("cover_letter", "One-shot first draft", one_shot.output.cover_letter_draft),
                ("reviewer", "One-shot self-review", one_shot.output.review),
            ]
            for stage, label, content in steps:
                if content is not None:
                    save_report(
                        stage,
                        json_object.validate_python(
                            {"step": label, "output": content.model_dump(mode="json")}
                        ),
                    )
        elif prepared.regenerate_research or saved_research is None:
            # step 1: research agent reads the posting and public company pages
            stage_progress(
                "research",
                "prepare",
                "Researching the company and typical role responsibilities"
                if request.research_mode == "generic" or not target.raw_description.strip()
                else "Reading the job and available public company sources",
            )
            if request.research_mode == "generic" or not target.raw_description.strip():
                research = analyze_generic_target(
                    target,
                    request.research_ai_options.apply(settings),
                    research_prompt=request.research_prompt,
                    company_url=request.company_research_url,
                    revision=saved_research.revision if saved_research else 1,
                    transport=transport,
                    on_usage=usage.record,
                    on_report=save_research,
                    on_completion=research_completion,
                    on_output=lambda output: save_output("research", output),
                )
            else:
                research = analyze_target(
                    target,
                    request.research_ai_options.apply(settings),
                    company_url=request.company_research_url,
                    transport=transport,
                    on_usage=usage.record,
                    on_report=save_research,
                    on_completion=research_completion,
                    on_output=lambda output: save_output("research", output),
                )
        else:
            research = saved_research
        research_data = json_object.validate_python(research.model_dump(mode="json"))
        with write_lock, Session(engine) as session, session.begin():
            row = session.get(JobDocument, request.request_id)
            if row is None:
                raise RuntimeError("Tailoring history disappeared")
            if row.status != "running":
                raise EditConflictError("This tailoring attempt is no longer running.")
            row.research = research_data
            # quotes we couldnt verify means we stop and let the user look at the sources
            if one_shot is None and not research.validated and research.approved_at is None:
                row.status = "awaiting_review"
                row.paused_at = None
                row.ai_usage = usage_snapshot()
                for item in row.stages:
                    if item.get("key") == "research":
                        item.update(
                            status="awaiting_review",
                            message="Generate a generic report or review sources",
                        )
                row.events.append(
                    _event(
                        len(row.events) + 1,
                        "validate",
                        "Research needs more context · generate a generic company and role report",
                    )
                )
                user = session.get(JobUserRecord, job_id)
                if user is not None and user.active_document_id == row.id:
                    user.active_document_id = None
                session.flush()
                return document_response(session, row, DocumentDetail)
        stage_progress(
            "research",
            "validate",
            (
                "Researched in the one-shot call; source quotations checked"
                if research.validated
                else "Researched in the one-shot call; some quotations could not be verified"
            )
            if one_shot is not None
            else "Research approved by you"
            if research.approved_at is not None
            else "Generic role report saved; available source quotations checked"
            if research.mode == "generic"
            else "Research saved and source quotations checked",
            "completed",
        )
        posting_target = tailoring_posting(target, research)
        writer_research = json_object.validate_python(
            research.model_dump(mode="json", exclude={"sources", "system_prompt", "ai_usage"})
        )
        keywords = research.analysis.keywords

        def write_resume(
            review_revision: dict[str, JsonValue] | None = None,
            feedback: str = "",
            first_draft: TailoredContent | None = None,
        ) -> GeneratedResume:
            diagnostics: PdfDiagnostics | None = None
            style = ""

            def keep_style(value: str) -> None:
                nonlocal style
                style = value

            def inspect_pdf(document: GeneratedResume, pdf: bytes) -> None:
                nonlocal diagnostics
                stage_progress("pdf_diagnostics", "validate", "Inspecting resume PDF text")
                diagnostics = diagnose_pdf(document, pdf, prepared.resume, posting_target, keywords)
                if style:
                    diagnostics.checks.append(
                        PdfDiagnosticCheck(
                            key="layout",
                            label="Bullet layout and page fill",
                            status="warning",
                            detail="The template measured bullets that break the one-or-two-"
                            "full-lines rule or blank space at the bottom of the page. The next "
                            "revision fixes them; any left after it are yours to adjust.",
                            missing=re.findall(r'^- "(.*)" \(', style, re.MULTILINE),
                        )
                    )

            try:
                stage_progress(
                    "resume", "prepare", "Using shared research and your complete profile"
                )
                resume = generate_resume(
                    posting_target,
                    resume=prepared.resume,
                    settings=(request.resume_ai_options or request.ai_options).apply(settings),
                    transport=transport,
                    on_usage=usage.record,
                    instructions=request.instructions,
                    on_progress=resume_progress,
                    research=writer_research,
                    on_report=resume_report,
                    on_output=lambda output: save_output("resume", output),
                    review_revision=review_revision,
                    on_pdf=inspect_pdf,
                    # style issues go to the reviewer revision, not a full redraft
                    retry_style=False,
                    revision_feedback=feedback,
                    on_style=keep_style,
                    first_draft=first_draft,
                )
                with write_lock, Session(engine) as session, session.begin():
                    row = session.get(JobDocument, request.request_id)
                    if row is None:
                        raise RuntimeError("Tailoring history disappeared")
                    row.resume = json_object.validate_python(resume.model_dump(mode="json"))
                    row.has_resume = True
                    row.unfitted_resume = None
                    row.layout_feedback = {**(row.layout_feedback or {}), "resume": style}
                    if diagnostics is not None:
                        row.pdf_diagnostics = [
                            item for item in row.pdf_diagnostics if item.get("document") != "resume"
                        ]
                        row.pdf_diagnostics.append(
                            json_object.validate_python(diagnostics.model_dump(mode="json"))
                        )
                stage_progress(
                    "resume",
                    "validate",
                    "Resume saved; evidence and PDF layout checked",
                    "completed",
                )
                return resume
            except Exception as error:
                kept = keep_previous("resume", error) if review_revision is not None else None
                if kept is not None:
                    return GeneratedResume.model_validate(kept)
                save_unfitted(error)
                stage_progress(
                    "resume",
                    "error",
                    _failure_message(error),
                    "failed",
                    details="".join(traceback.format_exception(error)),
                )
                raise

        def write_letter(
            review_revision: dict[str, JsonValue] | None = None,
            feedback: str = "",
            first_draft: LetterContent | None = None,
        ) -> GeneratedCoverLetter:
            diagnostics: PdfDiagnostics | None = None

            def inspect_pdf(document: GeneratedCoverLetter, pdf: bytes) -> None:
                nonlocal diagnostics
                stage_progress("pdf_diagnostics", "validate", "Inspecting cover-letter PDF text")
                diagnostics = diagnose_pdf(document, pdf, prepared.resume, posting_target, keywords)

            try:
                stage_progress(
                    "cover_letter", "prepare", "Using shared research and your complete profile"
                )
                letter = generate_cover_letter(
                    posting_target,
                    resume=prepared.resume,
                    settings=(request.cover_letter_ai_options or request.ai_options).apply(
                        settings
                    ),
                    transport=transport,
                    on_usage=usage.record,
                    instructions=request.instructions,
                    on_progress=letter_progress,
                    research=writer_research,
                    on_report=letter_report,
                    on_output=lambda output: save_output("cover_letter", output),
                    review_revision=review_revision,
                    on_pdf=inspect_pdf,
                    revision_feedback=feedback,
                    first_draft=first_draft,
                )
                with write_lock, Session(engine) as session, session.begin():
                    row = session.get(JobDocument, request.request_id)
                    if row is None:
                        raise RuntimeError("Tailoring history disappeared")
                    row.cover_letter = json_object.validate_python(letter.model_dump(mode="json"))
                    row.has_cover_letter = True
                    row.unfitted_cover_letter = None
                    if diagnostics is not None:
                        row.pdf_diagnostics = [
                            item
                            for item in row.pdf_diagnostics
                            if item.get("document") != "cover_letter"
                        ]
                        row.pdf_diagnostics.append(
                            json_object.validate_python(diagnostics.model_dump(mode="json"))
                        )
                stage_progress(
                    "cover_letter",
                    "validate",
                    "Cover letter saved; evidence and PDF layout checked",
                    "completed",
                )
                return letter
            except Exception as error:
                kept = keep_previous("cover_letter", error) if review_revision is not None else None
                if kept is not None:
                    return GeneratedCoverLetter.model_validate(kept)
                save_unfitted(error)
                stage_progress(
                    "cover_letter",
                    "error",
                    _failure_message(error),
                    "failed",
                    details="".join(traceback.format_exception(error)),
                )
                raise

        def polish_resume() -> bool:
            with Session(engine) as session:
                row = session.get(JobDocument, request.request_id)
                current = row.resume if row is not None else None
            if current is None:
                return False
            stage_progress("resume", "ai", "Rewriting only the bullets the template flagged")
            fixed = fix_flagged_bullets(
                GeneratedResume.model_validate(current),
                tailoring_source(prepared.resume),
                (request.resume_ai_options or request.ai_options).apply(settings),
                transport=transport,
                on_usage=usage.record,
                on_output=lambda output: save_output("resume", output),
                on_report=resume_report,
            )
            if fixed is None:
                stage_progress(
                    "resume", "validate", "Bullet fix kept the saved resume", "completed"
                )
                return False
            document, pdf, remaining = fixed
            stage_progress("pdf_diagnostics", "validate", "Inspecting resume PDF text")
            diagnostics = diagnose_pdf(document, pdf, prepared.resume, posting_target, keywords)
            with write_lock, Session(engine) as session, session.begin():
                row = session.get(JobDocument, request.request_id)
                if row is None:
                    raise RuntimeError("Tailoring history disappeared")
                row.resume = json_object.validate_python(document.model_dump(mode="json"))
                row.layout_feedback = {**(row.layout_feedback or {}), "resume": ""}
                row.pdf_diagnostics = [
                    item for item in row.pdf_diagnostics if item.get("document") != "resume"
                ]
                row.pdf_diagnostics.append(
                    json_object.validate_python(diagnostics.model_dump(mode="json"))
                )
            stage_progress(
                "resume",
                "validate",
                f"Flagged bullets fixed · {remaining} still to adjust by hand"
                if remaining
                else "Flagged bullets fixed; PDF layout rechecked",
                "completed",
            )
            return True

        if not prepared.resume_review:
            final = one_shot.output if one_shot is not None else None
            # step 2: resume and cover letter writers run at the same time
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="tailoring") as executor:
                resume_future = (
                    executor.submit(
                        partial(write_resume, first_draft=final.resume if final else None)
                    )
                    if request.include_resume
                    else None
                )
                letter_future = (
                    executor.submit(
                        partial(write_letter, first_draft=final.cover_letter if final else None)
                    )
                    if request.include_cover_letter
                    else None
                )
                if resume_future:
                    resume_future.result()
                if letter_future:
                    letter_future.result()
            stage_progress(
                "pdf_diagnostics", "validate", "Drafts rendered and PDF text checked", "completed"
            )
        if one_shot is not None:
            review = _one_shot_review(engine, request.request_id, one_shot, write_lock)
        else:
            # step 3: independent reviewer, it can ask the writers for one revision
            review = review_documents(
                engine,
                prepared,
                research,
                revise_resume=write_resume,
                revise_letter=write_letter,
                polish_resume=polish_resume,
                write_lock=write_lock,
                on_usage=usage.record,
                on_report=lambda content: save_report("reviewer", content),
                on_output=lambda output: save_output("reviewer", output),
                on_progress=lambda stage, message: stage_progress("reviewer", stage, message),
                transport=transport,
            )
        # findings the revision didnt fix get handed back to the user to decide
        if review.status == "awaiting_decision":
            stage_progress(
                "reviewer",
                "validate",
                "Choose how to handle the review findings",
                "awaiting_review",
            )
            stage_progress(
                "pdf_diagnostics",
                "validate",
                "PDF checks saved with the current drafts",
                "completed",
            )
            with write_lock, Session(engine) as session, session.begin():
                row = session.get(JobDocument, request.request_id)
                user = session.get(JobUserRecord, job_id)
                if row is None or user is None or user.active_document_id != row.id:
                    raise EditConflictError("This tailoring request no longer owns the job.")
                row.status = "awaiting_review"
                row.paused_at = None
                row.ai_usage = usage_snapshot()
                user.active_document_id = None
                session.flush()
                return document_response(session, row, DocumentDetail)
        stage_progress(
            "reviewer",
            "validate",
            "Review complete · remaining findings need your attention"
            if review.status == "needs_attention"
            else f"Self-review in the one-shot call · "
            f"{len(one_shot.output.review.findings)} finding(s) addressed in the final drafts"
            if one_shot is not None
            else "Independent review complete",
            "completed",
        )
        with Session(engine) as session:
            diagnostic_row = session.get(JobDocument, request.request_id)
            diagnostics = (
                [PdfDiagnostics.model_validate(item) for item in diagnostic_row.pdf_diagnostics]
                if diagnostic_row
                else []
            )
        warning_count = sum(
            check.status == "warning" for report in diagnostics for check in report.checks
        )
        stage_progress(
            "pdf_diagnostics",
            "validate",
            f"{len(diagnostics)} PDF report(s) saved · {warning_count} warning(s) to inspect",
            "completed",
        )
        with write_lock, Session(engine) as session, session.begin():
            row = session.get(JobDocument, request.request_id)
            user = session.get(JobUserRecord, job_id)
            if row is None or user is None or user.active_document_id != request.request_id:
                raise EditConflictError("This tailoring request no longer owns the job.")
            finished_at = int(time.time())
            row.status = "completed"
            row.paused_at = None
            row.finished_at = finished_at
            row.ai_usage = usage_snapshot()
            row.events.append(
                _event(
                    len(row.events) + 1,
                    "done",
                    "Documents and reports saved · ready for your review",
                )
            )
            if user.status == "new":
                user.status = "saved"
            user.updated_at = finished_at
            user.version += 1
            user.active_document_id = None
            record_activity(
                session.connection(),
                event_id=f"documents:{request.request_id}",
                kind="documents_generated",
                occurred_at=finished_at,
                data=ActivityData(
                    job_id=job_id,
                    company=target.company,
                    title=target.title,
                    document_id=request.request_id,
                    profile_revision=prepared.profile_revision,
                    has_resume=row.has_resume,
                    has_cover_letter=row.has_cover_letter,
                ),
            )
            session.flush()
            return document_response(session, row, DocumentDetail)
    except Exception as error:
        with write_lock, Session(engine) as session, session.begin():
            failed = session.get(JobDocument, request.request_id)
            if failed is not None and failed.status == "running":
                failed.paused_at = None
                failed.events.append(
                    _event(
                        len(failed.events) + 1,
                        "error",
                        "Tailoring did not complete · reports and any completed document "
                        "are preserved",
                        details="".join(traceback.format_exception(error)),
                    )
                )
                failed.status = "failed"
                failed.finished_at = int(time.time())
                failed.ai_usage = usage_snapshot()
                failed.error = _failure_message(error)
                _stop_stages(failed, _failure_message(error))
            elif failed is not None and failed.status == "cancelled":
                # calls that finished after cancel still cost money so count them
                failed.ai_usage = usage_snapshot()
            user = session.get(JobUserRecord, job_id)
            if user is not None and user.active_document_id == request.request_id:
                user.active_document_id = None
        raise
    finally:
        release_run(request.request_id)


def _one_shot_review(
    engine: Database, document_id: str, one_shot: OneShotResult, write_lock: RLock
) -> ApplicationReview:
    output = one_shot.output
    drafts = {
        key: draft
        for key, draft in (
            ("resume", output.resume_draft),
            ("cover_letter", output.cover_letter_draft),
        )
        if draft is not None
    }
    revisions: list[
        tuple[Literal["resume", "cover_letter"], BaseModel | None, BaseModel | None]
    ] = [
        ("resume", output.resume_draft, output.resume),
        ("cover_letter", output.cover_letter_draft, output.cover_letter),
    ]
    review = ApplicationReview(
        passes=[
            ReviewPass(
                round=1,
                analysis=output.review,
                document_hashes={
                    key: hashlib.sha256(
                        json.dumps(draft.model_dump(mode="json"), sort_keys=True).encode()
                    ).hexdigest()
                    for key, draft in drafts.items()
                },
                ai_usage=one_shot.usage,
            )
        ],
        revised_documents=[
            key
            for key, draft, final in revisions
            if draft is not None and final is not None and draft != final
        ],
        status="completed",
    )
    with write_lock, Session(engine) as session, session.begin():
        row = session.get(JobDocument, document_id)
        if row is None or row.status != "running":
            raise EditConflictError("This tailoring attempt is no longer running.")
        row.review = TypeAdapter(dict[str, JsonValue]).validate_python(
            review.model_dump(mode="json")
        )
    return review


def run_tailoring_background(
    engine: Database, prepared: PreparedTailoring, transport: httpx2.BaseTransport | None = None
) -> None:
    try:
        run_tailoring(engine, prepared, transport=transport)
    except Exception:
        return


def _expired(row: JobDocument | TailoringProcess) -> bool:
    if row.status != "running":
        return False
    if row.paused_at is not None:
        return pause_expired(row.paused_at)
    return (row.started_at or row.created_at) < int(time.time()) - 7200


def get_active_documents(engine: Database) -> list[TailoringProcess]:
    with Session(engine, read_only=True) as session:
        query = ReadQuery(
            "job_documents",
            Filter("status", value="running"),
            (Order("created_at", numeric=True), Order("@key")),
            fields=tuple(
                field for field in TailoringProcess.model_fields if field != "date_posted"
            ),
            source=True,
        )
        rows: list[TailoringProcess] = []
        while True:
            page = session.select(query, limit=1000, offset=len(rows), count=False).items
            rows.extend(
                TailoringProcess.model_validate({**row, "stages": row.get("stages") or []})
                for row in page
            )
            if len(page) < 1000:
                break
        processes: list[TailoringProcess] = []
        for row in rows:
            if _expired(row):
                get_document(engine, row.id)
            else:
                processes.append(row)
        job_ids = sorted({row.job_id for row in processes})
        dates: dict[str, int | None] = {}
        for position in range(0, len(job_ids), 1000):
            batch = job_ids[position : position + 1000]
            for job in session.select(
                ReadQuery("jobs", Filter("id", "in", list(batch)), fields=("id", "date_posted")),
                limit=len(batch),
                count=False,
            ).items:
                posted = job.get("date_posted")
                dates[str(job["id"])] = posted if isinstance(posted, int) else None
        for process in processes:
            process.date_posted = dates.get(process.job_id)
        return processes


def get_document(
    engine: Database, document_id: str, *, include_technical: bool = True
) -> DocumentDetail:
    with Session(engine, read_only=True) as session:
        if include_technical:
            row = session.get(JobDocument, document_id)
        else:
            fields = (
                "started_at",
                "request_snapshot",
                *(
                    field
                    for field in DocumentDetail.model_fields
                    if field not in {"date_posted", "reports", "profile_snapshot", "mode"}
                ),
            )
            rows = session.select(
                ReadQuery(
                    "job_documents", Filter("id", value=document_id), fields=fields, source=True
                ),
                limit=1,
                count=False,
            ).items
            candidate = (
                record_adapter(JobDocument).validate_python(
                    {key: value for key, value in rows[0].items() if value is not None}
                )
                if rows
                else None
            )
            if candidate is not None and not isinstance(candidate, JobDocument):
                raise TypeError("Invalid document projection")
            row = candidate
        if row is None:
            raise JobNotFoundError("Document not found")
        if not _expired(row):
            return document_response(session, row, DocumentDetail)
    with Session(engine) as session:
        row = session.get(JobDocument, document_id)
        if row is None:
            raise JobNotFoundError("Document not found")
        if _expired(row) and row.paused_at is not None:
            with session.begin():
                stop_expired_pause(session, row)
        elif _expired(row):
            with session.begin():
                row.status = "failed"
                row.finished_at = int(time.time())
                row.error = "Tailoring was interrupted or exceeded two hours. Start a new attempt."
                _stop_stages(row, row.error)
                row.events.append(_event(len(row.events) + 1, "error", row.error))
                user = session.get(JobUserRecord, row.job_id, hydrate=False)
                if user is not None and user.active_document_id == row.id:
                    user.active_document_id = None
        return document_response(session, row, DocumentDetail)
