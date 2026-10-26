from fastapi import HTTPException

from job_backend.common.models import AiSettings


def resume_ai_settings() -> AiSettings:
    try:
        return AiSettings.from_environment()
    except ValueError:
        raise HTTPException(
            status_code=503, detail="Configure JOB_AI settings to use resume AI"
        ) from None
