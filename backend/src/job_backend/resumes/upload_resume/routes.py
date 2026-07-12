from typing import Annotated

import httpx2
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile

from job_backend.common.ai_completion import AiCompletionError
from job_backend.common.models import AiModelOptions, AiSettings, ReasoningEffort
from job_backend.persistence.database import Database
from job_backend.resumes.dependencies import resume_ai_settings
from job_backend.resumes.models import UserResume
from job_backend.resumes.storage import ResumeNotFoundError, load_resume, save_resume
from job_backend.resumes.upload_resume.constants import MAX_UPLOAD_BYTES
from job_backend.resumes.upload_resume.upload import upload_resume


def create_router(engine: Database, *, transport: httpx2.BaseTransport | None = None) -> APIRouter:
    router = APIRouter()

    @router.get("/profile", summary="Read the complete user resume")
    def get_profile() -> UserResume:
        try:
            return load_resume(engine)
        except ResumeNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from None

    @router.put("/profile", summary="Replace the structured user resume")
    def put_profile(resume: UserResume) -> UserResume:
        return save_resume(engine, resume)

    @router.post("/upload", summary="Extract and save a user resume from an uploaded document")
    def upload(
        file: UploadFile,
        settings: Annotated[AiSettings, Depends(resume_ai_settings)],
        ai_model: Annotated[str | None, Form(max_length=200)] = None,
        ai_reasoning_effort: Annotated[ReasoningEffort | None, Form()] = None,
    ) -> UserResume:
        content = file.file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Resume upload exceeds 5 MiB")
        try:
            options = AiModelOptions(model=ai_model)
            if ai_reasoning_effort is not None:
                options.reasoning_effort = ai_reasoning_effort
            return upload_resume(
                file.filename or "",
                content,
                engine=engine,
                settings=options.apply(settings),
                transport=transport,
            )
        except AiCompletionError as error:
            raise HTTPException(status_code=502, detail=str(error)) from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    return router
