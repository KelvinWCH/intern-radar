from pydantic import Field

from job_backend.common.models import StrictModel
from job_backend.resumes.models import ResumeText


class LetterContent(StrictModel):
    """an opening, one or two body paragraphs and a closing"""

    paragraphs: list[ResumeText] = Field(min_length=3, max_length=4)
