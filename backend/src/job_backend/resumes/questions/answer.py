import json

import httpx2
from pydantic import ValidationError

from job_backend.common.ai_completion import AiCompletionError, complete_json
from job_backend.common.models import AiSettings
from job_backend.jobs.models import Job, JobResponse, TailoringJob
from job_backend.persistence.database import Database
from job_backend.profile.tailoring import tailoring_source
from job_backend.resumes.database import resume_database
from job_backend.resumes.models import UserResume
from job_backend.resumes.questions.constants import EVIDENCE_RETRY_PROMPT, QUESTION_PROMPT
from job_backend.resumes.questions.evidence import validate_evidence
from job_backend.resumes.questions.models import AnswerContent, QuestionAnswer, QuestionRequest
from job_backend.resumes.storage import load_resume
from job_backend.scrape.pipeline.models import ScrapedJob


def answer_question(
    question: str,
    *,
    job: Job | ScrapedJob | JobResponse | TailoringJob | None = None,
    additional_context: str | None = None,
    max_words: int = 200,
    resume: UserResume | None = None,
    engine: Database | None = None,
    settings: AiSettings | None = None,
    transport: httpx2.BaseTransport | None = None,
) -> QuestionAnswer:
    try:
        target = TailoringJob.model_validate(job, from_attributes=True) if job is not None else None
    except ValidationError:
        raise ValueError("Question answering needs a job with a full raw_description") from None
    if target is not None and not target.raw_description.strip():
        raise ValueError("Application answers need a job description.")
    try:
        request = QuestionRequest(
            question=question,
            job=target,
            additional_context=additional_context,
            max_words=max_words,
        )
    except ValidationError:
        raise ValueError(
            "Question answering needs a nonblank question, nonblank supplied context, "
            "and max_words from 1 to 1000"
        ) from None
    if resume is None:
        with resume_database(engine) as database:
            resume = load_resume(database)
    resume = tailoring_source(resume)
    config = settings or AiSettings.from_environment()
    user = json.dumps(
        {
            **request.model_dump(mode="json", exclude={"ai_options"}),
            "user_resume": resume.model_dump(mode="json"),
        },
        ensure_ascii=False,
    )
    if len(user) > config.max_document_chars:
        raise ValueError(
            "Question, context, job, and user resume exceed JOB_AI_MAX_DOCUMENT_CHARS; "
            "no data was truncated"
        )

    def draft(prompt: str) -> AnswerContent:
        return complete_json(
            config,
            system_prompt=prompt,
            user_content=user,
            response_model=AnswerContent,
            schema_name="application_question_answer",
            transport=transport,
        )

    content = draft(QUESTION_PROMPT)
    try:
        validate_evidence(content.evidence, resume, target, additional_context)
    except AiCompletionError:
        content = draft(QUESTION_PROMPT + EVIDENCE_RETRY_PROMPT)
        try:
            validate_evidence(content.evidence, resume, target, additional_context)
        except AiCompletionError as error:
            raise AiCompletionError(
                "The AI draft could not be verified against your resume and job details, "
                "even after retrying. Please try drafting again; your inputs are unchanged.",
                details=str(error),
            ) from error
    answer = content.answer.strip() if content.answer is not None else None
    word_count = len(answer.split()) if answer is not None else 0
    if word_count > request.max_words:
        raise AiCompletionError("AI answer exceeds the requested max_words limit")
    return QuestionAnswer(
        question=request.question,
        answer=answer,
        missing_information=content.missing_information,
        word_count=word_count,
    )
