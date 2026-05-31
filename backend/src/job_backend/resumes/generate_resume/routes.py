from typing import Annotated

import httpx2
from fastapi import APIRouter, Depends, HTTPException

from job_backend.common.ai_completion import AiCompletionError
from job_backend.common.models import AiModelOptions, AiSettings
from job_backend.jobs.models import JobCreate, JobResponse, TailoringJob
from job_backend.jobs.storage import save_user_job
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.resumes.compile_pdf.compile import PdfCompilerError
from job_backend.resumes.dependencies import resume_ai_settings
from job_backend.resumes.generate_resume.generate import generate_resume
from job_backend.resumes.model_catalog import read_model_catalog
from job_backend.resumes.models import GeneratedResume, ModelCatalog
from job_backend.resumes.storage import ResumeNotFoundError


def create_router(engine: Database, *, transport: httpx2.BaseTransport | None = None) -> APIRouter:
    router = APIRouter()

    @router.get("/ai-models", summary="List models available from the configured AI provider")
    def ai_models(settings: Annotated[AiSettings, Depends(resume_ai_settings)]) -> ModelCatalog:
        return read_model_catalog(settings, transport=transport)

    @router.get("/ai-settings", summary="Read the default tailoring model settings")
    def ai_settings(
        settings: Annotated[AiSettings, Depends(resume_ai_settings)],
    ) -> AiModelOptions:
        return AiModelOptions.from_settings(settings)

    @router.post("/generate", summary="Generate a structured resume tailored to a job")
    def generate(
        job: JobResponse | TailoringJob,
        settings: Annotated[AiSettings, Depends(resume_ai_settings)],
    ) -> GeneratedResume:
        try:
            resume = generate_resume(job, engine=engine, settings=settings, transport=transport)
            if isinstance(job, TailoringJob):
                with Session(engine) as session:
                    save_user_job(
                        session,
                        JobCreate.model_validate(job, from_attributes=True),
                        "user_auto_add",
                    )
            return resume
        except ResumeNotFoundError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None
        except AiCompletionError as error:
            raise HTTPException(status_code=502, detail=str(error)) from None
        except PdfCompilerError as error:
            raise HTTPException(status_code=503, detail=str(error)) from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    return router
