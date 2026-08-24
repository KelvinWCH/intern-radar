import httpx2
from fastapi import APIRouter

from job_backend.persistence.database import Database
from job_backend.resumes.compile_pdf.routes import router as pdf_router
from job_backend.resumes.generate_cover_letter.routes import create_router as create_letter_router
from job_backend.resumes.generate_resume.routes import create_router as create_generate_router
from job_backend.resumes.preview.routes import create_router as create_preview_router
from job_backend.resumes.profile.routes import create_router as create_profile_router
from job_backend.resumes.questions.routes import create_router as create_questions_router
from job_backend.resumes.render_cover_letter.routes import router as render_letter_router
from job_backend.resumes.render_latex.routes import router as render_router
from job_backend.resumes.transcript.routes import create_router as create_transcript_router
from job_backend.resumes.upload_resume.routes import create_router as create_upload_router


def create_router(engine: Database, *, transport: httpx2.BaseTransport | None = None) -> APIRouter:
    router = APIRouter(prefix="/resumes", tags=["resumes"])
    router.include_router(create_upload_router(engine, transport=transport))
    router.include_router(create_preview_router(engine))
    router.include_router(create_profile_router(engine))
    router.include_router(create_transcript_router(engine))
    router.include_router(create_generate_router(engine, transport=transport))
    router.include_router(render_router)
    router.include_router(create_letter_router(engine, transport=transport))
    router.include_router(render_letter_router)
    router.include_router(pdf_router)
    router.include_router(create_questions_router(engine, transport=transport))
    return router
