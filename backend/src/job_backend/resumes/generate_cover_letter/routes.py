from typing import Annotated

import httpx2
from fastapi import APIRouter, Depends, HTTPException

from job_backend.common.ai_completion import AiCompletionError
from job_backend.common.models import AiSettings
from job_backend.jobs.models import JobResponse, TailoringJob
from job_backend.persistence.database import Database
from job_backend.resumes.compile_pdf.compile import PdfCompilerError
from job_backend.resumes.dependencies import resume_ai_settings
from job_backend.resumes.generate_cover_letter.generate import generate_cover_letter
from job_backend.resumes.models import GeneratedCoverLetter
from job_backend.resumes.storage import ResumeNotFoundError


def create_router(engine: Database, *, transport: httpx2.BaseTransport | None = None) -> APIRouter:
    router = APIRouter()

    @router.post("/cover-letter/generate", summary="Generate a structured cover letter for a job")
    def generate(
        job: JobResponse | TailoringJob,
        settings: Annotated[AiSettings, Depends(resume_ai_settings)],
    ) -> GeneratedCoverLetter:
        try:
            return generate_cover_letter(job, engine=engine, settings=settings, transport=transport)
        except ResumeNotFoundError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None
        except AiCompletionError as error:
            raise HTTPException(status_code=502, detail=str(error)) from None
        except PdfCompilerError as error:
            raise HTTPException(status_code=503, detail=str(error)) from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    return router
