import zipfile
from collections.abc import Callable
from io import BytesIO
from typing import Annotated, Literal

import httpx2
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from pypdf import PdfWriter

from job_backend.common.ai_completion import AiCompletionError
from job_backend.common.models import AiSettings
from job_backend.jobs.models import (
    DocumentDetail,
    DocumentPage,
    DocumentSummary,
    DocumentTechnicalDetails,
    JobCreate,
    JobDocument,
    JobResponse,
    JobUserData,
    JobUserEdit,
    ResumeEdit,
    TailoringProcess,
    TailorRequest,
)
from job_backend.jobs.research_review import review_research
from job_backend.jobs.resume_edits import ResumeEditLayoutError, save_resume_edit
from job_backend.jobs.review_decisions import decide_review
from job_backend.jobs.storage import save_user_job
from job_backend.jobs.tailoring import (
    get_active_documents,
    get_document,
    prepare_tailoring,
    run_tailoring_background,
    tailor_job,
)
from job_backend.jobs.tailoring_control import cancel_tailoring, pause_tailoring, resume_tailoring
from job_backend.jobs.user_service import EditConflictError, JobNotFoundError, edit_user_data
from job_backend.persistence.database import Database
from job_backend.persistence.models import Filter, Order, ReadQuery
from job_backend.persistence.pagination import projected_history_page
from job_backend.persistence.session import Session
from job_backend.resumes.compile_pdf.compile import (
    PdfCompilerError,
    compile_document,
    compile_one_page,
)
from job_backend.resumes.constants import UNFITTED_DRAFT_PAGES
from job_backend.resumes.dependencies import resume_ai_settings
from job_backend.resumes.filenames import document_filename
from job_backend.resumes.models import (
    GeneratedResume,
    ResearchReview,
    ReviewDecision,
)
from job_backend.resumes.render_cover_letter.render import cover_letter_to_latex
from job_backend.resumes.render_latex.render import resume_to_latex
from job_backend.resumes.review.review import document_hash
from job_backend.resumes.storage import ResumeNotFoundError
from job_backend.resumes.transcript.storage import transcript_filename, transcript_pdf


def create_router(engine: Database, *, transport: httpx2.BaseTransport | None = None) -> APIRouter:
    router = APIRouter(tags=["applications"])

    @router.post("/jobs/for-tailoring", summary="Save a pasted job before tailoring")
    def add_for_tailoring(job: JobCreate) -> JobResponse:
        with Session(engine) as session:
            return save_user_job(session, job, "user_auto_add")

    @router.put("/jobs/{job_id}/user", summary="Edit application state and notes")
    def edit(job_id: str, body: JobUserEdit) -> JobUserData:
        try:
            return edit_user_data(engine, job_id, body)
        except JobNotFoundError as error:
            raise HTTPException(404, str(error)) from None
        except EditConflictError as error:
            raise HTTPException(409, str(error)) from None

    @router.post("/jobs/{job_id}/tailor-tasks", status_code=202, summary="Submit a tailoring job")
    def submit_tailoring(
        job_id: str,
        body: TailorRequest,
        background: BackgroundTasks,
        settings: Annotated[AiSettings, Depends(resume_ai_settings)],
    ) -> DocumentDetail:
        try:
            prepared = prepare_tailoring(engine, job_id, body, settings)
        except JobNotFoundError as error:
            raise HTTPException(404, str(error)) from None
        except (ResumeNotFoundError, EditConflictError) as error:
            raise HTTPException(409, str(error)) from None
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        if isinstance(prepared, DocumentDetail):
            return prepared
        background.add_task(run_tailoring_background, engine, prepared, transport)
        return prepared.document

    @router.post(
        "/documents/{document_id}/research-review",
        status_code=202,
        summary="Generate generic research, save edits, or resume writing",
    )
    def submit_research_review(
        document_id: str,
        body: ResearchReview,
        background: BackgroundTasks,
        settings: Annotated[AiSettings, Depends(resume_ai_settings)],
    ) -> DocumentDetail:
        try:
            prepared = review_research(engine, document_id, body, settings)
        except JobNotFoundError as error:
            raise HTTPException(404, str(error)) from None
        except EditConflictError as error:
            raise HTTPException(409, str(error)) from None
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        if isinstance(prepared, DocumentDetail):
            return prepared
        background.add_task(run_tailoring_background, engine, prepared, transport)
        return prepared.document

    @router.post(
        "/documents/{document_id}/application-review",
        status_code=202,
        summary="Keep review findings or request one selected revision",
    )
    def submit_application_review(
        document_id: str,
        body: ReviewDecision,
        background: BackgroundTasks,
        settings: Annotated[AiSettings, Depends(resume_ai_settings)],
    ) -> DocumentDetail:
        try:
            prepared = decide_review(engine, document_id, body, settings)
        except JobNotFoundError as error:
            raise HTTPException(404, str(error)) from None
        except EditConflictError as error:
            raise HTTPException(409, str(error)) from None
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        background.add_task(run_tailoring_background, engine, prepared, transport)
        return prepared.document

    def control(
        change: Callable[[Database, str], DocumentDetail], document_id: str
    ) -> DocumentDetail:
        try:
            return change(engine, document_id)
        except JobNotFoundError as error:
            raise HTTPException(404, str(error)) from None
        except EditConflictError as error:
            raise HTTPException(409, str(error)) from None

    @router.post("/documents/{document_id}/pause", summary="Pause tailoring before its next step")
    def pause(document_id: str) -> DocumentDetail:
        return control(pause_tailoring, document_id)

    @router.post("/documents/{document_id}/resume", summary="Continue paused tailoring")
    def resume(document_id: str) -> DocumentDetail:
        return control(resume_tailoring, document_id)

    @router.post("/documents/{document_id}/cancel", summary="Stop tailoring and keep its work")
    def cancel(document_id: str) -> DocumentDetail:
        return control(cancel_tailoring, document_id)

    @router.post("/jobs/{job_id}/tailor", summary="Research and save tailored documents for review")
    def tailor(
        job_id: str,
        body: TailorRequest,
        settings: Annotated[AiSettings, Depends(resume_ai_settings)],
    ) -> DocumentDetail:
        try:
            return tailor_job(engine, job_id, body, settings, transport=transport)
        except JobNotFoundError as error:
            raise HTTPException(404, str(error)) from None
        except (ResumeNotFoundError, EditConflictError) as error:
            raise HTTPException(409, str(error)) from None
        except AiCompletionError as error:
            raise HTTPException(502, str(error)) from None
        except PdfCompilerError as error:
            raise HTTPException(503, str(error)) from None
        except ValueError as error:
            raise HTTPException(422, str(error)) from None

    @router.get("/documents", summary="Browse saved tailoring attempts and documents")
    def history(
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
        job_id: str | None = None,
        cursor: Annotated[str | None, Query(max_length=1024)] = None,
    ) -> DocumentPage:
        if cursor is None and offset > 200:
            raise HTTPException(422, "Use cursor pagination for deeper history")
        with Session(engine, read_only=True) as session:
            if cursor is not None:
                try:
                    rows, following = projected_history_page(
                        session,
                        JobDocument,
                        "created_at",
                        limit=limit,
                        offset=offset,
                        cursor=cursor,
                        equal={"job_id": job_id} if job_id is not None else {},
                    )
                except ValueError as error:
                    raise HTTPException(422, str(error)) from None
                total = None
            else:
                page = session.select(
                    ReadQuery(
                        "job_documents",
                        Filter("job_id", value=job_id)
                        if job_id is not None
                        else Filter("created_at", "ne"),
                        (
                            Order("created_at", descending=True, numeric=True),
                            Order("@key", descending=True),
                        ),
                    ),
                    limit=limit,
                    offset=offset,
                )
                rows, total, following = page.items, page.total, None
            job_ids = [row["job_id"] for row in rows]
            dates = (
                session.select(
                    ReadQuery("jobs", Filter("id", "in", job_ids), fields=("id", "date_posted")),
                    limit=limit,
                    count=False,
                ).items
                if job_ids
                else []
            )
            date_by_id = {str(row["id"]): row["date_posted"] for row in dates}
            return DocumentPage(
                items=[
                    DocumentSummary.model_validate(
                        {**row, "date_posted": date_by_id.get(str(row["job_id"]))}
                    )
                    for row in rows
                ],
                total=total,
                limit=limit,
                offset=offset,
                next_cursor=following,
            )

    @router.get("/documents/active", summary="Read all running tailoring processes")
    def active_documents(response: Response) -> list[TailoringProcess]:
        response.headers["Cache-Control"] = "no-store"
        return get_active_documents(engine)

    @router.get("/documents/{document_id}/technical", summary="Inspect full generation logs")
    def technical(document_id: str) -> DocumentTechnicalDetails:
        with Session(engine, read_only=True) as session:
            rows = session.select(
                ReadQuery(
                    "job_documents",
                    Filter("id", value=document_id),
                    fields=("id", "reports", "profile_snapshot"),
                    source=True,
                ),
                limit=1,
                count=False,
            ).items
            if not rows:
                raise HTTPException(404, "Document not found")
            return DocumentTechnicalDetails.model_validate(
                {
                    **rows[0],
                    "reports": rows[0].get("reports") or [],
                }
            )

    @router.get("/documents/{document_id}", summary="Read a saved resume and cover letter")
    def document(document_id: str) -> DocumentDetail:
        try:
            return get_document(engine, document_id, include_technical=False)
        except JobNotFoundError as error:
            raise HTTPException(404, str(error)) from None

    @router.put("/documents/{document_id}/resume", summary="Save your edits to a tailored resume")
    def edit_resume(document_id: str, body: ResumeEdit) -> DocumentDetail:
        try:
            return save_resume_edit(engine, document_id, body)
        except JobNotFoundError as error:
            raise HTTPException(404, str(error)) from None
        except EditConflictError as error:
            raise HTTPException(409, str(error)) from None
        except ResumeEditLayoutError as error:
            raise HTTPException(422, str(error)) from None
        except PdfCompilerError as error:
            raise HTTPException(503, str(error)) from None

    @router.get(
        "/documents/{document_id}/{kind}/{format}",
        response_class=Response,
        summary="Download a saved document as PDF or LaTeX",
    )
    def download(
        document_id: str,
        kind: Literal["resume", "cover-letter"],
        format: Literal["pdf", "tex"],
    ) -> Response:
        rendered, filename = _render_saved(document(document_id), kind, format)
        return _file_response(rendered, filename, format)

    @router.get(
        "/documents/{document_id}/package",
        response_class=Response,
        summary="Download the resume, cover letter, and transcript together",
    )
    def download_package(
        document_id: str,
        format: Annotated[Literal["pdf", "zip"], Query()] = "pdf",
        transcript: Annotated[bool, Query()] = True,
    ) -> Response:
        result = document(document_id)
        kinds: list[Literal["resume", "cover-letter"]] = []
        if result.cover_letter is not None:
            kinds.append("cover-letter")
        if result.resume is not None:
            kinds.append("resume")
        if not kinds:
            raise HTTPException(404, "This attempt has no generated documents")
        files: list[tuple[str, bytes]] = []
        for kind in kinds:
            rendered, filename = _render_saved(result, kind, "pdf")
            files.append((filename, rendered.encode() if isinstance(rendered, str) else rendered))
        attachment = transcript_pdf(engine) if transcript else None
        if attachment is not None:
            files.append((transcript_filename(engine), attachment))
        writer = result.resume or result.cover_letter
        applicant = writer.name if writer else ""
        filename = document_filename(result.company, applicant, "application", format)
        return _file_response(_bundle(files, format), filename, format)

    @router.get(
        "/documents/{document_id}/unfitted/{kind}/{format}",
        response_class=Response,
        summary="Download the closest draft of a document that never fit one page",
    )
    def download_unfitted(
        document_id: str,
        kind: Literal["resume", "cover-letter"],
        format: Literal["pdf", "tex"],
    ) -> Response:
        result = document(document_id)
        draft = result.unfitted_resume if kind == "resume" else result.unfitted_cover_letter
        if draft is None:
            raise HTTPException(404, "No draft that missed one page was kept for this document")
        source = (
            resume_to_latex(draft.document)
            if isinstance(draft.document, GeneratedResume)
            else cover_letter_to_latex(draft.document)
        )
        rendered: str | bytes = source
        if format == "pdf":
            try:
                rendered = compile_document(source, max_pages=UNFITTED_DRAFT_PAGES)
            except PdfCompilerError as error:
                raise HTTPException(503, str(error)) from None
            except ValueError as error:
                raise HTTPException(422, str(error)) from None
        filename = document_filename(result.company, draft.document.name, kind, format)
        return _file_response(
            rendered, filename.removesuffix(f".{format}") + f"_Draft.{format}", format
        )

    return router


def _render_saved(
    result: DocumentDetail, kind: Literal["resume", "cover-letter"], format: Literal["pdf", "tex"]
) -> tuple[str | bytes, str]:
    content = result.resume if kind == "resume" else result.cover_letter
    previously_validated = content is not None and any(
        report.document == kind.replace("-", "_")
        and report.document_sha256 == document_hash(content)
        for report in result.pdf_diagnostics
    )
    if (
        not previously_validated
        and not (kind == "resume" and result.resume_edited_at is not None)
        and result.status != "completed"
        and not any(
            stage.key == kind.replace("-", "_") and stage.status == "completed"
            for stage in result.stages
        )
    ):
        raise HTTPException(409, "This document has not completed validation")
    if kind == "resume" and result.resume:
        source = resume_to_latex(result.resume)
        applicant = result.resume.name
    elif kind == "cover-letter" and result.cover_letter:
        source = cover_letter_to_latex(result.cover_letter)
        applicant = result.cover_letter.name
    else:
        raise HTTPException(404, "This document was not generated")
    rendered: str | bytes = source
    if format == "pdf":
        try:
            rendered = compile_one_page(source)
        except PdfCompilerError as error:
            raise HTTPException(503, str(error)) from None
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
    return rendered, document_filename(result.company, applicant, kind, format)


def _bundle(files: list[tuple[str, bytes]], format: Literal["pdf", "zip"]) -> bytes:
    output = BytesIO()
    if format == "zip":
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for filename, content in files:
                archive.writestr(filename, content)
    else:
        writer = PdfWriter()
        for _, content in files:
            writer.append(BytesIO(content))
        writer.write(output)
    return output.getvalue()


_MEDIA_TYPES = {"pdf": "application/pdf", "tex": "application/x-tex", "zip": "application/zip"}


def _file_response(
    content: str | bytes, filename: str, format: Literal["pdf", "tex", "zip"]
) -> Response:
    return Response(
        content=content,
        media_type=_MEDIA_TYPES[format],
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
