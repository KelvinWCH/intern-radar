from pydantic import Field

from job_backend.common.models import StrictModel
from job_backend.resumes.models import UserResume


class ResumeProfileState(StrictModel):
    resume: UserResume | None
    revision: int
    updated_at: int | None


class ResumeProfileEdit(StrictModel):
    resume: UserResume
    revision: int = Field(ge=0)
