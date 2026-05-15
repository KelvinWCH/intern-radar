from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import AbstractContextManager, nullcontext
from typing import Literal

import httpx2
from pydantic import JsonValue, TypeAdapter

from job_backend.common.models import AiUsage, CompletionOutput
from job_backend.jobs.models import JobDocument, PreparedTailoring
from job_backend.jobs.user_service import EditConflictError
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.resumes.models import (
    ApplicationReview,
    GeneratedCoverLetter,
    GeneratedResume,
    PdfDiagnostics,
    ProgressCallback,
    ResearchReport,
    ReviewFinding,
)
from job_backend.resumes.review.context import review_history
from job_backend.resumes.review.review import review_application


def polish_feedback(row: JobDocument, key: Literal["resume", "cover_letter"]) -> str:
    layout = (row.layout_feedback or {}).get(key)
    feedback = layout if isinstance(layout, str) else ""
    report = next(
        (item for item in row.pdf_diagnostics if item.get("document") == key == "resume"), None
    )
    checks = PdfDiagnostics.model_validate(report) if report else None
    missing = (
        []
        if checks is None or report is None
        else checks.missing_supported_keywords
        if "missing_supported_keywords" in report
        else checks.missing_supported_skills
    )
    if missing:
        feedback += (
            "\n# Job keywords missing from the draft\nThe posting uses these terms, the "
            "candidate's profile supports them, and the draft does not use them: "
            + ", ".join(missing)
            + ". Use each one, spelled exactly, in a bullet of an entry that supports it or by "
            "selecting it from Technical Skills inventory indices. Never attribute one to an "
            "entry that does not support it."
        )
    return feedback


def review_documents(
    engine: Database,
    prepared: PreparedTailoring,
    research: ResearchReport,
    *,
    revise_resume: Callable[[dict[str, JsonValue], str], GeneratedResume],
    revise_letter: Callable[[dict[str, JsonValue], str], GeneratedCoverLetter],
    polish_resume: Callable[[], bool] | None = None,
    write_lock: AbstractContextManager[object] | None = None,
    on_output: Callable[[CompletionOutput], None] | None = None,
    on_usage: Callable[[AiUsage], None],
    on_report: Callable[[dict[str, JsonValue]], None],
    on_progress: ProgressCallback,
    transport: httpx2.BaseTransport | None = None,
) -> ApplicationReview:
    request = prepared.request
    json_object = TypeAdapter(dict[str, JsonValue])
    review = prepared.document.review if prepared.resume_review else None
    review = review or ApplicationReview()

    lock = write_lock or nullcontext()

    def save() -> None:
        with lock, Session(engine) as session, session.begin():
            row = session.get(JobDocument, request.request_id)
            if row is None or row.status != "running":
                raise EditConflictError("This tailoring attempt is no longer running.")
            row.review = json_object.validate_python(review.model_dump(mode="json"))

    def load() -> JobDocument:
        with Session(engine) as session:
            row = session.get(JobDocument, request.request_id)
            if row is None:
                raise EditConflictError("This tailoring attempt no longer exists.")
            return row

    def polish_pending() -> bool:
        row = load()
        return any(
            polish_feedback(row, key) and key not in review.revised_documents
            for key in ("resume", "cover_letter")
        )

    def polish() -> None:
        row = load()
        layout = (row.layout_feedback or {}).get("resume")
        if (
            polish_resume is not None
            and isinstance(layout, str)
            and layout
            and "resume" not in review.revised_documents
            and polish_feedback(row, "resume") == layout
            and not (
                polish_feedback(row, "cover_letter")
                and "cover_letter" not in review.revised_documents
            )
        ):
            review.status = "revising"
            save()
            on_progress("retry", "Fixing the measured bullet layout with a targeted rewrite")
            if polish_resume() and "resume" not in review.revised_documents:
                review.revised_documents.append("resume")
            review.status = "reviewing"
            save()
            return
        revise_findings([], {})

    def revise_findings(findings: list[ReviewFinding], guidance: dict[int, str]) -> None:
        review.status = "revising"
        save()
        on_progress(
            "retry",
            "Revising selected findings using the saved profile evidence"
            if findings
            else "Fixing measured bullet layout and missing required skills",
        )
        row = load()
        resume = GeneratedResume.model_validate(row.resume) if row.resume else None
        letter = GeneratedCoverLetter.model_validate(row.cover_letter) if row.cover_letter else None
        writers: list[
            tuple[
                Literal["resume", "cover_letter"],
                GeneratedResume | GeneratedCoverLetter | None,
                Callable[[dict[str, JsonValue], str], object],
            ]
        ] = [("resume", resume, revise_resume), ("cover_letter", letter, revise_letter)]
        futures: dict[Literal["resume", "cover_letter"], Future[object]] = {}
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="revision") as executor:
            for key, document, revise in writers:
                selected = [
                    {**finding.model_dump(mode="json"), "user_guidance": guidance.get(index, "")}
                    for index, finding in enumerate(findings)
                    if finding.document in {key, "both"}
                ]
                feedback = polish_feedback(row, key)
                if document is None or not (
                    selected or (feedback and key not in review.revised_documents)
                ):
                    continue
                payload = json_object.validate_python(
                    {
                        "previous_draft": document.model_dump(mode="json", exclude={"ai_usage"}),
                        "findings": selected,
                        "review_history": review_history(review),
                    }
                )
                futures[key] = executor.submit(revise, payload, feedback)
        for key, future in futures.items():
            if future.exception() is None and key not in review.revised_documents:
                review.revised_documents.append(key)
        save()
        for future in futures.values():
            future.result()
        review.status = "reviewing"
        save()

    if prepared.resume_review:
        if review.status == "needs_attention":
            if polish_pending():
                polish()
                review.status = "needs_attention"
                save()
            return review
        decision = review.decisions[-1]
        previous = review.passes[-1].analysis.findings
        selected = [item for item in decision.decisions if item.action == "revise"]
        revise_findings(
            [previous[item.finding_index] for item in selected],
            {index: item.guidance for index, item in enumerate(selected)},
        )

    for cycle in range(1 if prepared.resume_review else 2):
        round_number = len(review.passes) + 1
        on_progress(
            "ai",
            "Reviewing both documents against the profile and research"
            if round_number == 1
            else "Checking the revised documents",
        )
        row = load()
        if row.status != "running":
            raise EditConflictError("This tailoring attempt is no longer running.")
        resume = GeneratedResume.model_validate(row.resume) if row.resume else None
        letter = GeneratedCoverLetter.model_validate(row.cover_letter) if row.cover_letter else None
        result = review_application(
            prepared.target,
            prepared.resume,
            research,
            resume,
            letter,
            (request.reviewer_ai_options or request.ai_options).apply(prepared.settings),
            round_number=round_number,
            previous_review=review,
            diagnostics=[PdfDiagnostics.model_validate(item) for item in row.pdf_diagnostics],
            transport=transport,
            on_usage=on_usage,
            on_output=on_output,
            on_report=on_report,
        )
        review.passes.append(result)
        save()
        actionable = [
            finding for finding in result.analysis.findings if finding.severity != "suggestion"
        ]
        unresolved = [
            finding
            for index, finding in enumerate(result.analysis.findings)
            if finding.severity != "suggestion" and index not in result.acknowledged_finding_indices
        ]
        if not unresolved:
            if polish_pending():
                polish()
            review.status = "needs_attention" if actionable else "completed"
            save()
            return review
        if (
            any(finding.category == "requirements" for finding in unresolved)
            or prepared.resume_review
            or cycle == 1
        ):
            review.status = "awaiting_decision"
            save()
            return review
        revise_findings(unresolved, {})
    raise RuntimeError("Unreachable reviewer state")
