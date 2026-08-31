from typing import Literal, Self

from pydantic import Field, model_validator

from job_backend.common.models import AiModelOptions, StrictModel
from job_backend.jobs.models import JobResponse, TailoringJob
from job_backend.resumes.models import ResumeText


class AnswerEvidence(StrictModel):
    """exact quotes from a profile field, entry, job or extra context"""

    source: Literal[
        "profile",
        "experience",
        "projects",
        "education",
        "skills",
        "additional_sections",
        "job",
        "additional_context",
    ]
    source_index: int | None = Field(
        ge=0,
        description="Zero-based entry index; null for profile, job, and additional_context",
    )
    source_quotes: list[ResumeText] = Field(min_length=1)


class AnswerContent(StrictModel):
    """either a supported answer or the details needed before one can be written"""

    answer: ResumeText | None
    missing_information: list[ResumeText]
    evidence: list[AnswerEvidence]

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.answer is None:
            if not self.missing_information or self.evidence:
                raise ValueError("A missing answer requires missing information and no evidence")
        elif self.missing_information or not self.evidence:
            raise ValueError("An answer requires evidence and no missing information")
        return self


class QuestionAnswer(StrictModel):
    question: ResumeText
    answer: ResumeText | None
    missing_information: list[ResumeText]
    word_count: int = Field(ge=0, le=1000)


class QuestionRequest(StrictModel):
    question: ResumeText
    job: JobResponse | TailoringJob | None = None
    additional_context: ResumeText | None = Field(
        default=None,
        description="User-supplied facts relevant to this question, such as personal motivation, "
        "availability, or company details. Distinguish applicant facts from employer facts.",
    )
    max_words: int = Field(default=200, ge=1, le=1000)
    ai_options: AiModelOptions = Field(default_factory=AiModelOptions)


class ContextCompletionRequest(StrictModel):
    text: str = Field(max_length=20000)
    purpose: Literal["question", "context", "guidance"]
    question: str = Field(default="", max_length=10000)
    additional_context: str = Field(default="", max_length=20000)
    job: TailoringJob | None = None
    document_id: str | None = Field(default=None, min_length=1, max_length=100)
    review_issue: str = Field(default="", max_length=10000)
    ai_options: AiModelOptions = Field(default_factory=AiModelOptions)


class ContextCompletionContent(StrictModel):
    """keep evidence private and allow abstaining when facts are missing"""

    continuation: str | None = Field(max_length=500)
    evidence: list[AnswerEvidence]

    @model_validator(mode="after")
    def validate_continuation(self) -> Self:
        if self.continuation is None:
            if self.evidence:
                raise ValueError("An absent continuation must have no evidence")
        elif not self.continuation.strip() or any(char in self.continuation for char in "\r\n"):
            raise ValueError("A continuation must be a nonblank single line")
        return self


class ContextCompletion(StrictModel):
    continuation: str | None = Field(max_length=500)
    model: str
