from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, ClassVar, Literal, Self

from pydantic import (
    ConfigDict,
    Field,
    HttpUrl,
    JsonValue,
    TypeAdapter,
    field_validator,
    model_validator,
)

from job_backend.common.models import AiModelOptions, AiSettings, AiUsage, StrictModel
from job_backend.jobs.company_priority import company_tier
from job_backend.jobs.constants import RAW_DESCRIPTION_LIMIT, TAILORING_DESCRIPTION_LIMIT
from job_backend.jobs.descriptions import clean_description, description_for_tailoring
from job_backend.jobs.employer_ids import employer_job_id
from job_backend.jobs.identity import job_document_id
from job_backend.matching.models import JobMatchView
from job_backend.persistence.models import StoredRecord
from job_backend.resumes.models import (
    ApplicationReview,
    GeneratedCoverLetter,
    GeneratedResume,
    GenerationReport,
    PdfDiagnostics,
    ResearchReport,
    TailoringEvent,
    TailoringStage,
    UnfittedCoverLetter,
    UnfittedResume,
    UserResume,
)
from job_backend.resumes.one_shot.models import OneShotStep
from job_backend.scrape.pipeline.models import Qualifications

ClosedReason = Literal["not_listed", "upstream_closed", "link_check"]

LinkStatus = Literal["open", "closed", "unknown"]


class LinkCheck(StrictModel):
    checked_at: int = Field(ge=0, description="Check time, Unix seconds in UTC.")
    status: LinkStatus
    detail: str = Field(min_length=1, max_length=500)
    url: str = Field(description="Posting URL that was checked.")
    final_url: str | None = Field(
        default=None, description="Page reached after redirects, when one was read."
    )


ApplicationStatus = Literal[
    "new", "saved", "applied", "interviewing", "offered", "rejected", "withdrawn"
]
DocumentStatus = Literal["running", "awaiting_review", "completed", "failed", "cancelled"]


class DocumentSummary(StrictModel):
    id: str
    job_id: str
    company: str
    title: str
    status: DocumentStatus
    created_at: int
    date_posted: int | None = Field(
        default=None,
        ge=0,
        description="Current known posting date of the target job, UTC Unix seconds.",
    )
    finished_at: int | None
    has_resume: bool
    has_cover_letter: bool
    error: str | None
    ai_usage: AiUsage | None = None


class JobUserData(StrictModel):
    status: ApplicationStatus = "new"
    notes: str = ""
    applied_at: int | None = None
    follow_up_at: int | None = None
    updated_at: int | None = None
    version: int = 0
    documents: list[DocumentSummary] = Field(default_factory=list[DocumentSummary])


class JobUserEdit(StrictModel):
    status: ApplicationStatus
    notes: str = Field(max_length=50_000)
    applied_at: int | None = Field(default=None, ge=0)
    follow_up_at: int | None = Field(default=None, ge=0)
    version: int = Field(ge=0)


class SavedJobDescription(StrictModel):
    raw_description: str | None


MatchReason = Literal[
    "identical_extraction_input", "same_url", "same_employer_id", "conflicting_employer_ids"
]


class DuplicatedJob(StrictModel):
    id: str
    source: str
    external_id: str
    company: str
    title: str
    source_job_id: str | None
    application_url: str | None
    source_url: str | None
    listing_url: str | None = None
    raw_description: str | None
    first_seen_at: int
    date_posted: int | None = Field(default=None, ge=0)
    match_reason: MatchReason

    @field_validator("application_url", "source_url", "listing_url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        return str(TypeAdapter(HttpUrl).validate_python(value)) if value is not None else None


class DuplicatedJobs(StrictModel):
    items: list[DuplicatedJob] = Field(default_factory=list[DuplicatedJob])


@dataclass(kw_only=True)
class IdentityState(StoredRecord):
    collection: ClassVar[str] = "job_identity_state"
    key_fields: ClassVar[tuple[str, ...]] = ("id",)
    id: str = "current"
    version: int = 0
    refreshed_at: int = 0
    changed: int = 0


SourceType = Literal["scraped", "user_added", "user_auto_add"]
UserSourceType = Literal["user_added", "user_auto_add"]
# why a posting waits for you: a bot check, LinkedIn, or robots.txt said not to open it
ReviewReason = Literal["security_challenge", "linkedin_blocked", "robots_disallowed"]


JobText = Annotated[str, Field(min_length=1, max_length=2000, pattern=r"\S")]


class JobFields(StrictModel):
    company: JobText = "Not specified"
    title: JobText = "Not specified"
    source_job_id: JobText | None = None
    application_url: str | None = None
    apply_url: str | None = None
    company_url: str | None = None
    locations: list[JobText] = Field(default_factory=list, max_length=200)
    terms: list[JobText] = Field(default_factory=list, max_length=200)
    category: JobText | None = None
    sponsorship: JobText | None = None
    active: bool | None = True
    date_posted: int | None = Field(default=None, ge=0)
    date_updated: int | None = Field(default=None, ge=0)
    summary: str | None = Field(default=None, max_length=200_000)
    cleaned_description: str | None = Field(default=None, max_length=RAW_DESCRIPTION_LIMIT)
    qualifications: Qualifications | None = None

    @field_validator("application_url", "apply_url", "company_url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        return str(TypeAdapter(HttpUrl).validate_python(value)) if value is not None else None

    @field_validator("company", "title", "source_job_id", "category", "sponsorship")
    @classmethod
    def trim_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("source_job_id")
    @classmethod
    def normalize_employer_id(cls, value: str | None) -> str | None:
        return employer_job_id(value)

    @field_validator("locations", "terms")
    @classmethod
    def trim_lists(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values))


class JobDetails(JobFields):
    raw_description: str | None = Field(default=None, max_length=RAW_DESCRIPTION_LIMIT)


class JobEdit(JobDetails):
    version: int = Field(ge=0)


class JobOverview(StrictModel):
    total: int
    statuses: dict[str, int]
    sources: list[str]


class JobReview(StrictModel):
    version: int = Field(ge=0)


class TailorRequest(StrictModel):
    request_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )
    include_resume: bool = True
    include_cover_letter: bool = True
    ai_options: AiModelOptions = Field(default_factory=AiModelOptions)
    research_ai_options: AiModelOptions = Field(default_factory=AiModelOptions)
    resume_ai_options: AiModelOptions | None = None
    cover_letter_ai_options: AiModelOptions | None = None
    reviewer_ai_options: AiModelOptions | None = None
    company_research_url: str | None = Field(default=None, max_length=2000)
    research_mode: Literal["job_description", "generic"] = "job_description"
    research_prompt: str | None = Field(default=None, max_length=2000)
    mode: Literal["staged", "one_shot"] = "staged"
    one_shot_ai_options: AiModelOptions | None = None

    @field_validator("company_research_url")
    @classmethod
    def validate_company_url(cls, value: str | None) -> str | None:
        return str(TypeAdapter(HttpUrl).validate_python(value)) if value else None

    instructions: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional guidance for emphasis and tone; it cannot authorize new facts.",
    )

    @model_validator(mode="after")
    def require_document(self) -> Self:
        if not self.include_resume and not self.include_cover_letter:
            raise ValueError("Select a resume or cover letter")
        return self


class DocumentDetail(DocumentSummary):
    mode: Literal["staged", "one_shot"] = "staged"
    one_shot_step: OneShotStep | None = None

    profile_revision: int
    job_description: str
    paused_at: int | None = None
    resume: GeneratedResume | None
    generated_resume: GeneratedResume | None = None
    resume_edited_at: int | None = None
    resume_revision: int = 0
    cover_letter: GeneratedCoverLetter | None
    ai_options: AiModelOptions | None = None
    research_ai_options: AiModelOptions | None = None
    resume_ai_options: AiModelOptions | None = None
    cover_letter_ai_options: AiModelOptions | None = None
    reviewer_ai_options: AiModelOptions | None = None
    review: ApplicationReview | None = None
    unfitted_resume: UnfittedResume | None = None
    unfitted_cover_letter: UnfittedCoverLetter | None = None
    pdf_diagnostics: list[PdfDiagnostics] = Field(default_factory=list[PdfDiagnostics])
    research: ResearchReport | None = None
    stages: list[TailoringStage] = Field(default_factory=list[TailoringStage])
    reports: list[GenerationReport] = Field(default_factory=list[GenerationReport])
    profile_snapshot: dict[str, JsonValue] | None = None
    events: list[TailoringEvent] = Field(default_factory=list[TailoringEvent])


class ResumeEdit(StrictModel):
    revision: int = Field(ge=0, description="The resume_revision these edits started from.")
    resume: GeneratedResume = Field(
        description="The complete edited resume. Its AI usage is ignored; the saved usage stays."
    )


class DocumentTechnicalDetails(StrictModel):
    id: str
    reports: list[GenerationReport] = Field(default_factory=list[GenerationReport])
    profile_snapshot: dict[str, JsonValue] | None = None


class TailoringProcess(DocumentSummary):
    started_at: int | None
    paused_at: int | None = None
    stages: list[TailoringStage] = Field(default_factory=list[TailoringStage])


class DocumentPage(StrictModel):
    items: list[DocumentSummary]
    total: int | None
    limit: int
    offset: int
    next_cursor: str | None = None


@dataclass(kw_only=True)
class JobUserRecord(StoredRecord):
    collection: ClassVar[str] = "job_user_data"
    key_fields: ClassVar[tuple[str, ...]] = ("job_id",)
    job_id: str = ""
    status: str = "new"
    notes: str = ""
    applied_at: int | None = None
    follow_up_at: int | None = None
    updated_at: int = 0
    version: int = 1
    active_document_id: str | None = None
    documents: list[DocumentSummary] = field(default_factory=list[DocumentSummary])


@dataclass(kw_only=True)
class JobDocument(StoredRecord):
    collection: ClassVar[str] = "job_documents"
    key_fields: ClassVar[tuple[str, ...]] = ("id",)
    id: str = ""
    job_id: str = ""
    company: str = ""
    title: str = ""
    job_description: str = ""
    profile_revision: int = 0
    status: str = ""
    one_shot_step: str | None = None
    created_at: int = 0
    started_at: int | None = None
    paused_at: int | None = None
    finished_at: int | None = None
    has_resume: bool = False
    has_cover_letter: bool = False
    error: str | None = None
    ai_usage: dict[str, JsonValue] | None = None
    ai_options: dict[str, JsonValue] | None = None
    research_ai_options: dict[str, JsonValue] | None = None
    resume_ai_options: dict[str, JsonValue] | None = None
    cover_letter_ai_options: dict[str, JsonValue] | None = None
    reviewer_ai_options: dict[str, JsonValue] | None = None
    review: dict[str, JsonValue] | None = None
    layout_feedback: dict[str, JsonValue] | None = None
    unfitted_resume: dict[str, JsonValue] | None = None
    unfitted_cover_letter: dict[str, JsonValue] | None = None
    pdf_diagnostics: list[dict[str, JsonValue]] = field(default_factory=list[dict[str, JsonValue]])
    research: dict[str, JsonValue] | None = None
    stages: list[dict[str, JsonValue]] = field(default_factory=list[dict[str, JsonValue]])
    reports: list[dict[str, JsonValue]] = field(default_factory=list[dict[str, JsonValue]])
    profile_snapshot: dict[str, JsonValue] | None = None
    request_snapshot: dict[str, JsonValue] | None = None
    target_snapshot: dict[str, JsonValue] | None = None
    resume: dict[str, JsonValue] | None = None
    generated_resume: dict[str, JsonValue] | None = None
    resume_edited_at: int | None = None
    resume_revision: int = 0
    cover_letter: dict[str, JsonValue] | None = None
    events: list[dict[str, JsonValue]] = field(default_factory=lambda: list[dict[str, JsonValue]]())


class JobDisplay(StrictModel):
    id: str
    details_version: int = Field(default=0, ge=0)
    details_updated_at: int | None = None
    deleted_at: int | None = Field(default=None, ge=0)
    user: JobUserData = Field(default_factory=JobUserData)

    prestige: bool = False
    company_tier: Literal["tech", "known"] | None = None

    @model_validator(mode="after")
    def derive_prestige(self) -> Self:
        self.company_tier = company_tier(self.company)
        self.prestige = self.company_tier is not None
        return self

    @field_validator("user", mode="before")
    @classmethod
    def default_user_data(cls, value: object) -> object:
        return JobUserData() if value is None else value

    source: str
    source_type: SourceType = "scraped"
    review_reason: ReviewReason | None = None
    external_id: str
    source_job_id: str | None

    @field_validator("source_job_id")
    @classmethod
    def normalize_employer_id(cls, value: str | None) -> str | None:
        return employer_job_id(value)

    company: str
    title: str
    application_url: str | None
    apply_url: str | None
    company_url: str | None
    locations: list[str]
    category: str | None
    terms: list[str]
    sponsorship: str | None
    upstream_source: str | None
    active: bool | None
    is_visible: bool | None
    date_posted: int | None
    date_updated: int | None
    summary: str | None
    source_url: str | None
    is_canada_internship: bool | None
    is_toronto_area: bool | None
    job_hash: str = Field(
        pattern=r"^[0-9a-f]{64}$", description="Stable SHA-256 identity of source and external ID."
    )
    content_hash: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        description="SHA-256 used to detect changes in the latest imported job data.",
    )
    first_seen_at: int = Field(ge=0, description="First local observation, Unix seconds in UTC.")
    last_seen_at: int = Field(
        ge=0, description="Latest processed observation, Unix seconds in UTC."
    )
    last_changed_at: int | None = Field(
        ge=0, description="Local metadata change time in UTC Unix seconds; unknown for legacy rows."
    )
    closed_at: int | None = Field(
        default=None, ge=0, description="When this installation found the posting closed."
    )
    closed_reason: ClosedReason | None = None
    closed_detail: str | None = None
    link_check: LinkCheck | None = None
    match: JobMatchView | None = Field(
        default=None, description="Stored relevance to the profile; absent until scored."
    )

    @field_validator("application_url", "apply_url", "company_url", "source_url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        return str(TypeAdapter(HttpUrl).validate_python(value)) if value is not None else None


class JobCreate(JobFields):
    raw_description: str = Field(default="", max_length=RAW_DESCRIPTION_LIMIT)

    @model_validator(mode="after")
    def require_target_context(self) -> Self:
        if not (self.cleaned_description or self.raw_description).strip() and (
            self.company == "Not specified" or self.title == "Not specified"
        ):
            raise ValueError("Enter a company and role, or supply a job description.")
        return self


@dataclass(kw_only=True)
class Job(StoredRecord):
    collection: ClassVar[str] = "jobs"
    key_fields: ClassVar[tuple[str, ...]] = ("id",)
    id: str = ""
    details_version: int = 0
    details_updated_at: int | None = None
    deleted_at: int | None = None
    detail_overrides: dict[str, JsonValue] | None = None
    user: JobUserRecord | None = None
    source: str = ""
    source_type: SourceType = "scraped"
    review_reason: ReviewReason | None = None
    external_id: str = ""
    source_job_id: str | None = None
    deduplication_key: str | None = None
    job_url_hash: str | None = None
    extraction_fingerprint: str | None = None
    company: str = ""
    title: str = ""
    application_url: str | None = None
    apply_url: str | None = None
    company_url: str | None = None
    locations: list[str] = field(default_factory=list[str])
    category: str | None = None
    terms: list[str] = field(default_factory=list[str])
    qualifications: dict[str, JsonValue] | None = None
    sponsorship: str | None = None
    upstream_source: str | None = None
    active: bool | None = None
    is_visible: bool | None = None
    date_posted: int | None = None
    date_updated: int | None = None
    summary: str | None = None
    raw_description: str | None = None
    cleaned_description: str | None = None
    job_hash: str = ""
    content_hash: str = ""
    source_url: str | None = None
    raw_payload: dict[str, JsonValue] | None = None
    last_changed_at: int | None = None
    first_seen_at: int = 0
    last_seen_at: int = 0
    is_canada_internship: bool | None = None
    is_toronto_area: bool | None = None
    closed_at: int | None = None
    closed_reason: ClosedReason | None = None
    closed_detail: str | None = None
    link_check: dict[str, JsonValue] | None = None

    def assign_identity(self) -> None:
        if not self.id:
            self.id = job_document_id(self.source, self.external_id, self.application_url)


class JobListItem(JobDisplay):
    raw_description: None = None
    cleaned_description: None = None
    raw_payload: None = None
    qualifications: None = None
    copies: int = Field(
        default=1,
        ge=1,
        description="Saved postings of this job across boards that this row stands for.",
    )


class JobResponse(JobDisplay):
    duplicated_jobs: DuplicatedJobs = Field(default_factory=DuplicatedJobs)
    qualifications: Qualifications | None
    raw_description: str | None
    cleaned_description: str | None = None
    raw_payload: dict[str, JsonValue] | None

    @model_validator(mode="after")
    def derive_description(self) -> Self:
        if self.cleaned_description is None:
            self.cleaned_description = clean_description(
                self.raw_description, source_url=self.source_url or self.application_url
            )
        return self


class JobPage(StrictModel):
    items: list[JobListItem]
    total: int
    limit: int
    offset: int


class TailoringJob(JobCreate):
    model_config = ConfigDict(revalidate_instances="always")

    raw_description: str = Field(default="", max_length=TAILORING_DESCRIPTION_LIMIT)
    qualifications: Qualifications | None = None

    def metadata(self) -> dict[str, object]:
        return self.model_dump(
            mode="json", exclude={"raw_description", "cleaned_description", "qualifications"}
        )

    @model_validator(mode="before")
    @classmethod
    def use_cleaned_description(cls, value: object) -> object:
        if isinstance(value, Job | JobResponse):
            return {
                "company": value.company,
                "title": value.title,
                "application_url": value.application_url,
                "company_url": value.company_url,
                "qualifications": value.qualifications,
                "raw_description": description_for_tailoring(
                    value.raw_description, value.cleaned_description, allow_empty=True
                ),
            }
        if isinstance(value, TailoringJob):
            return value
        if isinstance(value, JobCreate):
            fields = value.model_dump()
            fields["raw_description"] = description_for_tailoring(
                value.raw_description, value.cleaned_description, allow_empty=True
            )
            fields["cleaned_description"] = None
            return fields
        if isinstance(value, dict):
            fields = TypeAdapter(dict[str, object]).validate_python(value)
            cleaned = fields.get("cleaned_description")
            if isinstance(cleaned, str):
                fields["raw_description"] = description_for_tailoring(
                    None, cleaned, allow_empty=True
                )
                fields["cleaned_description"] = None
            return fields
        return value


@dataclass(frozen=True)
class PreparedTailoring:
    request: TailorRequest
    settings: AiSettings
    target: TailoringJob
    resume: UserResume
    profile_revision: int
    document: DocumentDetail
    regenerate_research: bool = False
    resume_review: bool = False
