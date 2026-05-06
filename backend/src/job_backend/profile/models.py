from pydantic import Field

from job_backend.common.models import StrictModel
from job_backend.resumes.models import UserResume


class CandidatePreferences(StrictModel):
    target_roles: list[str] = Field(default_factory=list[str], max_length=100)
    preferred_locations: list[str] = Field(default_factory=list[str], max_length=100)
    available_terms: list[str] = Field(default_factory=list[str], max_length=30)
    graduation_year: int | None = Field(default=None, ge=1900, le=2200)
    year_of_study: int | None = Field(default=None, ge=1, le=20)
    currently_enrolled: bool | None = None
    returning_to_study: bool | None = None
    requires_sponsorship: bool | None = None
    experience_years: float | None = Field(default=None, ge=0, le=80)
    gpa: float | None = Field(default=None, ge=0, le=100)
    gpa_scale: float | None = Field(default=None, gt=0, le=100)
    work_authorization: str | None = Field(default=None, max_length=3000)


class ResumeSettings(StrictModel):
    min_experience_bullets: int = Field(default=3, ge=1, le=6)
    min_project_bullets: int = Field(default=2, ge=1, le=6)


class CandidateStory(StrictModel):
    title: str = Field(min_length=1, max_length=500, pattern=r"\S")
    related_experience: str | None = Field(default=None, max_length=1000)
    situation: str | None = Field(default=None, max_length=10000)
    task: str | None = Field(default=None, max_length=10000)
    action: str = Field(min_length=1, max_length=20000, pattern=r"\S")
    result: str | None = Field(default=None, max_length=10000)
    learning: str | None = Field(default=None, max_length=10000)
    skills: list[str] = Field(default_factory=list[str], max_length=100)
    evidence: list[str] = Field(default_factory=list[str], max_length=100)


class CandidateAnswer(StrictModel):
    question: str = Field(min_length=1, max_length=5000, pattern=r"\S")
    answer: str = Field(min_length=1, max_length=20000, pattern=r"\S")
    context: str | None = Field(default=None, max_length=5000)


class UserProfile(UserResume):
    about: str | None = Field(default=None, max_length=20000)
    goals: str | None = Field(default=None, max_length=10000)
    stories: list[CandidateStory] = Field(default_factory=list[CandidateStory], max_length=200)
    answers: list[CandidateAnswer] = Field(default_factory=list[CandidateAnswer], max_length=200)
    preferences: CandidatePreferences = Field(default_factory=CandidatePreferences)
    resume_settings: ResumeSettings = Field(default_factory=ResumeSettings)


class UserProfileState(StrictModel):
    profile: UserProfile | None
    revision: int
    updated_at: int | None


class UserProfileEdit(StrictModel):
    profile: UserProfile
    revision: int = Field(ge=0)
