import time
from collections.abc import Sequence
from math import ceil

from pydantic import JsonValue, TypeAdapter

from job_backend.jobs.document_response import document_response
from job_backend.jobs.models import DocumentDetail, JobDocument, ResumeEdit, TailoringJob
from job_backend.jobs.tailoring import tailoring_posting
from job_backend.jobs.user_service import EditConflictError, JobNotFoundError
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.profile.models import UserProfile
from job_backend.resumes.compile_pdf.compile import DocumentLayoutError, compile_one_page_measured
from job_backend.resumes.compile_pdf.diagnostics import diagnose_pdf
from job_backend.resumes.compile_pdf.models import PdfCompiler
from job_backend.resumes.constants import LINE_POINTS
from job_backend.resumes.generation import keep_fitted
from job_backend.resumes.models import (
    GeneratedResume,
    PdfDiagnostics,
    ResearchReport,
    UnfittedResume,
)
from job_backend.resumes.render_latex.render import resume_to_latex
from job_backend.resumes.review.review import document_hash

_CheckInputs = tuple[UserProfile, TailoringJob, Sequence[str]]


class ResumeEditLayoutError(ValueError):
    pass


def save_resume_edit(
    engine: Database, document_id: str, edit: ResumeEdit, *, compiler: PdfCompiler | None = None
) -> DocumentDetail:
    with Session(engine) as session:
        row = _editable(session, document_id, edit.revision)
        current = _current_resume(row)
        if row.resume is not None and document_hash(edit.resume) == document_hash(current):
            return document_response(session, row, DocumentDetail)
        inputs = _check_inputs(row)
    edited = edit.resume.model_copy(update={"ai_usage": current.ai_usage})
    try:
        measured = compile_one_page_measured(resume_to_latex(edited), compiler=compiler)
    except DocumentLayoutError as error:
        raise ResumeEditLayoutError(_layout_message(error)) from None
    edited = keep_fitted(edited, measured.fitted)
    diagnostics = diagnose_pdf(edited, measured.pdf, *inputs) if inputs is not None else None
    json_object = TypeAdapter(dict[str, JsonValue])
    with Session(engine) as session, session.begin():
        row = _editable(session, document_id, edit.revision)
        current = _current_resume(row)
        if row.resume is not None and document_hash(edited) == document_hash(current):
            return document_response(session, row, DocumentDetail)
        generated = (
            GeneratedResume.model_validate(row.generated_resume)
            if row.generated_resume is not None
            else current
        )
        restored = document_hash(generated) == document_hash(edited)
        row.generated_resume = (
            None if restored else json_object.validate_python(generated.model_dump(mode="json"))
        )
        row.resume_edited_at = None if restored else int(time.time())
        row.resume = json_object.validate_python(edited.model_dump(mode="json"))
        row.has_resume = True
        row.unfitted_resume = None
        row.resume_revision += 1
        row.pdf_diagnostics = [
            item for item in row.pdf_diagnostics if item.get("document") != "resume"
        ] + _diagnostics_rows(diagnostics)
        session.flush()
        return document_response(session, row, DocumentDetail)


def _editable(session: Session, document_id: str, revision: int) -> JobDocument:
    row = session.get(JobDocument, document_id)
    if row is None:
        raise JobNotFoundError("Document not found")
    if row.status == "running":
        raise EditConflictError("Tailoring is still running. Edit the resume once it finishes.")
    if row.status == "awaiting_review":
        raise EditConflictError(
            "This attempt is waiting for your review. Resolve it before editing the resume."
        )
    if row.resume is None and row.unfitted_resume is None:
        raise JobNotFoundError("This attempt has no resume to edit")
    if row.resume_revision != revision:
        raise EditConflictError(
            "This resume was saved again since you started editing. Reload it, then reapply "
            "your edits."
        )
    return row


def _current_resume(row: JobDocument) -> GeneratedResume:
    if row.resume is not None:
        return GeneratedResume.model_validate(row.resume)
    return UnfittedResume.model_validate(row.unfitted_resume).document


def _check_inputs(row: JobDocument) -> _CheckInputs | None:
    if row.profile_snapshot is None:
        return None
    profile = UserProfile.model_validate(row.profile_snapshot)
    target = (
        TailoringJob.model_validate(row.target_snapshot)
        if row.target_snapshot
        else TailoringJob(company=row.company, title=row.title, raw_description=row.job_description)
    )
    if row.research is None:
        return profile, target, ()
    research = ResearchReport.model_validate(row.research)
    return profile, tailoring_posting(target, research), research.analysis.keywords


def _diagnostics_rows(diagnostics: PdfDiagnostics | None) -> list[dict[str, JsonValue]]:
    if diagnostics is None:
        return []
    return [TypeAdapter(dict[str, JsonValue]).validate_python(diagnostics.model_dump(mode="json"))]


def _layout_message(error: DocumentLayoutError) -> str:
    if error.overflow_points > 0:
        lines = ceil(error.overflow_points / LINE_POINTS)
        return (
            f"Your edits run about {lines} printed line{'s' if lines != 1 else ''} past one page, "
            "so they were not saved. Shorten or remove something, then save again."
        )
    return f"Your edits were not saved. {error}."
