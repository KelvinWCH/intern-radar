from typing import Annotated

import httpx2
from fastapi import APIRouter, Depends, HTTPException

from job_backend.common.ai_completion import AiCompletionError
from job_backend.common.models import AiSettings
from job_backend.persistence.database import Database
from job_backend.resumes.dependencies import resume_ai_settings
from job_backend.resumes.questions.answer import answer_question
from job_backend.resumes.questions.complete import complete_context
from job_backend.resumes.questions.models import (
    ContextCompletion,
    ContextCompletionRequest,
    QuestionAnswer,
    QuestionRequest,
)
from job_backend.resumes.storage import ResumeNotFoundError


def create_router(engine: Database, *, transport: httpx2.BaseTransport | None = None) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/questions/answer", summary="Answer an application question using the full resume"
    )
    def answer(
        request: QuestionRequest,
        settings: Annotated[AiSettings, Depends(resume_ai_settings)],
    ) -> QuestionAnswer:
        try:
            return answer_question(
                request.question,
                job=request.job,
                additional_context=request.additional_context,
                max_words=request.max_words,
                engine=engine,
                settings=request.ai_options.apply(settings),
                transport=transport,
            )
        except ResumeNotFoundError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None
        except AiCompletionError as error:
            raise HTTPException(status_code=502, detail=str(error)) from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    @router.post(
        "/questions/complete", summary="Suggest a sentence from the saved profile and context"
    )
    def suggest(
        request: ContextCompletionRequest,
        settings: Annotated[AiSettings, Depends(resume_ai_settings)],
    ) -> ContextCompletion:
        try:
            return complete_context(request, engine, settings, transport=transport)
        except ResumeNotFoundError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None
        except AiCompletionError as error:
            raise HTTPException(status_code=502, detail=str(error)) from None
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    return router
