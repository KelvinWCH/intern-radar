from typing import Literal

from job_backend.common.models import StrictModel
from job_backend.resumes.generate_cover_letter.models import LetterContent
from job_backend.resumes.generate_resume.models import TailoredContent
from job_backend.resumes.models import ResearchAnalysis, ReviewAnalysis

OneShotStep = Literal["research", "draft", "review", "revise"]


class OneShotOutput(StrictModel):
    """research, first drafts, their critique and the revised final documents"""

    research: ResearchAnalysis
    resume_draft: TailoredContent | None
    cover_letter_draft: LetterContent | None
    review: ReviewAnalysis
    resume: TailoredContent | None
    cover_letter: LetterContent | None
