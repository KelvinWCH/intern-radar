import json

import httpx2

from job_backend.common.ai_completion import AiCompletionError, complete_json
from job_backend.common.models import AiSettings
from job_backend.persistence.database import Database
from job_backend.resumes.database import resume_database
from job_backend.resumes.models import UserResume
from job_backend.resumes.storage import save_resume
from job_backend.resumes.upload_resume.constants import UPLOAD_PROMPT
from job_backend.resumes.upload_resume.documents import extract_resume_text


def upload_resume(
    filename: str,
    content: bytes,
    *,
    engine: Database | None = None,
    settings: AiSettings | None = None,
    transport: httpx2.BaseTransport | None = None,
) -> UserResume:
    config = settings or AiSettings.from_environment()
    source = extract_resume_text(filename, content, max_chars=config.max_document_chars)
    resume = complete_json(
        config,
        system_prompt=UPLOAD_PROMPT,
        user_content=json.dumps({"resume_text": source}, ensure_ascii=False),
        response_model=UserResume,
        schema_name="user_resume",
        transport=transport,
    )
    if len(resume.model_dump_json()) > config.max_document_chars:
        raise AiCompletionError("Extracted user resume exceeds JOB_AI_MAX_DOCUMENT_CHARS")
    if not (resume.education or resume.experience or resume.projects or resume.skills):
        raise AiCompletionError(
            "AI did not find usable resume education, experience, projects, or skills"
        )
    with resume_database(engine) as database:
        return save_resume(database, resume)
