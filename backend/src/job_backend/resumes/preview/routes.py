from fastapi import APIRouter, HTTPException, Response

from job_backend.persistence.database import Database
from job_backend.resumes.compile_pdf.compile import DocumentLayoutError, PdfCompilerError
from job_backend.resumes.models import DraftPreview, GeneratedResume
from job_backend.resumes.preview.preview import preview_draft, preview_resume
from job_backend.resumes.storage import ResumeNotFoundError, load_resume


def create_router(engine: Database) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/profile/pdf",
        summary="Preview the current saved source resume",
        response_class=Response,
        responses={200: {"content": {"application/pdf": {}}}},
    )
    def profile_pdf() -> Response:
        try:
            resume = load_resume(engine)
            pdf = preview_resume(resume)
        except ResumeNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from None
        except DocumentLayoutError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except PdfCompilerError as error:
            raise HTTPException(status_code=503, detail=str(error)) from None
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'inline; filename="source-resume.pdf"',
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.post("/draft-preview", summary="Show how an edited tailored resume prints")
    def draft_preview(resume: GeneratedResume, response: Response) -> DraftPreview:
        response.headers["Cache-Control"] = "private, no-store"
        try:
            return preview_draft(resume)
        except DocumentLayoutError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except PdfCompilerError as error:
            raise HTTPException(status_code=503, detail=str(error)) from None

    return router
