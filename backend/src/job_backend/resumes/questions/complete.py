import json

import httpx2

from job_backend.common.ai_completion import AiCompletionError, complete_json
from job_backend.common.models import AiSettings
from job_backend.jobs.models import JobDocument, TailoringJob
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.profile.models import UserProfile
from job_backend.profile.tailoring import tailoring_source
from job_backend.resumes.questions.constants import COMPLETION_PROMPT
from job_backend.resumes.questions.evidence import validate_evidence
from job_backend.resumes.questions.models import (
    ContextCompletion,
    ContextCompletionContent,
    ContextCompletionRequest,
)
from job_backend.resumes.storage import load_resume


def complete_context(
    request: ContextCompletionRequest,
    engine: Database,
    settings: AiSettings,
    *,
    transport: httpx2.BaseTransport | None = None,
) -> ContextCompletion:
    config = request.ai_options.apply(settings)
    config = config.model_copy(
        update={
            "timeout_seconds": min(config.timeout_seconds, 20),
            "max_output_tokens": min(config.max_output_tokens or 2048, 2048),
            "reasoning_effort": None,
        }
    )
    if request.purpose == "question" and not request.text.strip():
        return ContextCompletion(continuation=None, model=config.model)
    target = request.job
    if request.document_id:
        with Session(engine) as session:
            row = session.get(JobDocument, request.document_id)
            if row is None or row.profile_snapshot is None:
                raise ValueError("This application has no saved profile for suggestions.")
            profile = UserProfile.model_validate(row.profile_snapshot)
            target = TailoringJob(
                company=row.company, title=row.title, raw_description=row.job_description
            )
    else:
        profile = load_resume(engine)
    profile = tailoring_source(profile)
    context = "\n".join(part for part in (request.additional_context, request.text) if part)
    payload = {
        "text": request.text,
        "purpose": request.purpose,
        "question": request.question,
        "additional_context": context,
        "review_issue": request.review_issue,
        "job": target.model_dump(mode="json") if target else None,
        "user_resume": profile.model_dump(mode="json"),
    }
    user = json.dumps(payload, ensure_ascii=False)
    if len(user) > config.max_document_chars:
        raise ValueError(
            "Suggestion context exceeds JOB_AI_MAX_DOCUMENT_CHARS; no data was truncated"
        )
    content = complete_json(
        config,
        system_prompt=COMPLETION_PROMPT,
        user_content=user,
        response_model=ContextCompletionContent,
        schema_name="context_sentence_completion",
        transport=transport,
    )
    if content.continuation:
        if len(content.continuation.split()) > 60:
            raise AiCompletionError("AI suggestion exceeds the sentence length limit")
        if request.purpose == "context" and not content.evidence:
            raise AiCompletionError("AI context suggestion is missing source evidence")
        validate_evidence(content.evidence, profile, target, context or None)
    return ContextCompletion(continuation=content.continuation, model=config.model)
