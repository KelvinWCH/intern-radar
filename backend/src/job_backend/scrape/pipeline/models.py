import hashlib
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, ClassVar, Literal, Protocol, Self

from pydantic import Field, HttpUrl, JsonValue, TypeAdapter, field_validator, model_validator

from job_backend.common.environment import load_environment
from job_backend.common.models import StrictModel
from job_backend.jobs.employer_ids import employer_job_id
from job_backend.persistence.models import StoredRecord
from job_backend.scrape.models import ScrapePerformance, ScrapeTrigger


@dataclass(kw_only=True)
class ApiDetailCache(StoredRecord):
    collection: ClassVar[str] = "api_detail_cache"
    key_fields: ClassVar[tuple[str, ...]] = ("url_hash",)

    url_hash: str = ""
    url: str = ""
    content: str = ""
    fetched_at: int = 0


@dataclass(kw_only=True)
class ChallengedHost(StoredRecord):
    collection: ClassVar[str] = "challenged_hosts"
    key_fields: ClassVar[tuple[str, ...]] = ("host",)
    host: str = ""
    streak: int = 0
    last_challenge_at: int = 0
    skip_until: int = 0


class JobLink(StrictModel):
    url: str
    listing_url: str
    date_posted: int | None = Field(ge=0)
    external_id: str | None = Field(default=None, min_length=1)
    listing_data: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("url", "listing_url")
    @classmethod
    def validate_link(cls, value: str) -> str:
        TypeAdapter(HttpUrl).validate_python(value)
        return value


class RawDocument(StrictModel):
    content: str = Field(min_length=1, description="Original scraped text, HTML, or JSON.")
    source_url: str = Field(description="URL the raw data was scraped from.")
    media_type: str = Field(default="text/plain", description="Format of the raw data.")
    external_id: str | None = Field(
        default=None,
        min_length=1,
        description="Trusted job-board record ID or URL identity, if available.",
    )

    listing_url: str | None = None
    application_url: str | None = None
    apply_url: str | None = None
    date_posted: int | None = Field(default=None, ge=0)
    listing_data: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("source_url", "listing_url", "application_url", "apply_url")
    @classmethod
    def validate_source_url(cls, value: str | None) -> str | None:
        if value is not None:
            TypeAdapter(HttpUrl).validate_python(value)
        return value


@dataclass(frozen=True)
class ScrapeResult:
    fetched: int
    documents: list[RawDocument] = field(default_factory=list[RawDocument])
    links: list[JobLink] = field(default_factory=list[JobLink])
    listed_urls: tuple[str, ...] = ()


@dataclass(frozen=True)
class FetchFailure:
    error: Exception
    url: str


@dataclass(frozen=True)
class FetchResult:
    payload: bytes | None
    etag: str | None
    failures: tuple[FetchFailure, ...] = ()


@dataclass(frozen=True)
class JobSource:
    name: str
    fetch: Callable[[str | None], FetchResult]
    scrape: Callable[[bytes], ScrapeResult]
    terms: tuple[str, ...] = ()
    require_recent_dates: bool = True
    links_are_apply_urls: bool = True
    page_renderer: Literal["http", "browser", "auto"] | None = None
    complete_listing: bool = False


class EducationRequirements(StrictModel):
    """education requirements as stated, no guessing a study year"""

    degree_levels: list[str] = Field(description="Accepted degrees, such as Bachelor's or PhD.")
    fields_of_study: list[str] = Field(description="Accepted subjects or academic disciplines.")
    year_of_study_required: int | None = Field(
        ge=1,
        description="Explicitly required academic year as an integer, such as 3 for third year. "
        "Use null when absent or when several years are accepted; list those separately.",
    )
    eligible_years_of_study: list[Annotated[int, Field(ge=1)]] = Field(
        description="Explicitly accepted academic years; empty when not stated."
    )
    graduation_years: list[Annotated[int, Field(ge=1900, le=2200)]] = Field(
        description="Explicitly accepted graduation calendar years, not internship start years."
    )
    currently_enrolled: bool | None = Field(
        description="Whether current enrollment is explicitly required; null when unstated."
    )
    must_return_to_study: bool | None = Field(
        description="Whether returning to school after the placement is explicitly required."
    )
    minimum_gpa: float | None = Field(ge=0, description="Explicitly stated minimum GPA, if any.")
    gpa_scale: float | None = Field(
        gt=0, description="Explicitly stated GPA scale; never assume 4."
    )

    @field_validator("degree_levels", "fields_of_study")
    @classmethod
    def normalize_lists(cls, values: list[str]) -> list[str]:
        return sorted(set(values))

    @field_validator("eligible_years_of_study", "graduation_years")
    @classmethod
    def normalize_years(cls, values: list[int]) -> list[int]:
        return sorted(set(values))


class Qualifications(StrictModel):
    """education, skills, experience and eligibility from the full job page"""

    education: EducationRequirements
    required_skills: list[str]
    preferred_skills: list[str]
    tech_stack: list[str] = Field(
        description="Explicitly named programming languages, libraries, platforms, and tools."
    )
    minimum_experience_years: float | None = Field(
        ge=0, description="Explicit minimum years of work experience; not years of study."
    )
    experience_requirements: list[str] = Field(
        description="Required experience details that cannot be represented by a number of years."
    )
    certifications: list[str]
    languages: list[str] = Field(description="Required spoken or written languages, not code.")
    work_authorization: str | None
    visa_sponsorship_available: bool | None = Field(
        description="Employer explicitly offers or rules out visa sponsorship. "
        "An application question about needing sponsorship is not an answer; use null."
    )
    security_clearance: str | None
    other_requirements: list[str]

    @field_validator(
        "required_skills",
        "preferred_skills",
        "tech_stack",
        "experience_requirements",
        "certifications",
        "languages",
        "other_requirements",
    )
    @classmethod
    def normalize_lists(cls, values: list[str]) -> list[str]:
        return sorted(set(values))


class ExtractedJob(StrictModel):
    """job fields read by ai, use null or empty lists when missing"""

    is_canada_internship: bool = Field(
        description="AI decision: this is an internship, co-op, or student research placement "
        "with a Canadian work location "
        "or explicit permission to work remotely from Canada."
    )
    is_toronto_area: bool = Field(
        description="AI decision: at least one work location is Toronto, Markham, or a nearby "
        "Greater Toronto Area community. Canada-wide remote alone is false."
    )
    source_job_id: str | None = Field(
        min_length=1,
        description="Employer or ATS requisition ID, if explicitly available. "
        "Never a GitHub row ID, invented ID, URL hash, or local database ID.",
    )
    company: str = Field(min_length=1)
    title: str = Field(min_length=1)
    application_url: str = Field(min_length=1, description="Full job description page URL.")
    apply_url: str | None = Field(
        description="Application form or apply-button URL, when available; may match the job page."
    )
    company_url: str | None
    locations: list[str]
    category: str | None
    terms: list[str]
    qualifications: Qualifications
    sponsorship: str | None
    upstream_source: str | None = Field(
        description="Where the job board says this listing came from, if provided."
    )
    active: bool | None
    is_visible: bool | None
    date_posted: int | None = Field(
        ge=0, description="Posting time reported by the job board, UTC Unix seconds."
    )
    date_updated: int | None = Field(
        ge=0, description="Update time reported by the job board, UTC Unix seconds."
    )
    summary: str | None = Field(
        description="Short AI-written overview of the role, responsibilities, and key requirements."
    )

    @field_validator("source_job_id")
    @classmethod
    def validate_source_job_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Use null when no employer job ID is available")
        return employer_job_id(value)

    @field_validator("locations", "terms")
    @classmethod
    def normalize_lists(cls, values: list[str]) -> list[str]:
        return sorted(set(values))

    @field_validator("application_url", "apply_url", "company_url")
    @classmethod
    def validate_job_url(cls, value: str | None) -> str | None:
        return str(TypeAdapter(HttpUrl).validate_python(value)) if value is not None else None


class ExtractionResult(StrictModel):
    """every job found in one document, or an empty list for non job content"""

    jobs: list[ExtractedJob]


class JobNormalizer(Protocol):
    @property
    def cache_key(self) -> str: ...

    @property
    def max_calls_per_scrape(self) -> int: ...

    def extract(self, document: RawDocument) -> ExtractionResult: ...


class ScrapedJob(ExtractedJob):
    extraction_fingerprint: str | None = Field(default=None, exclude=True)

    source: str = Field(min_length=1, description="Job board name, such as simplify-summer2027.")
    external_id: str = Field(
        min_length=1,
        description="Job board record ID, or an ID calculated from its application URL.",
    )
    source_url: str | None = Field(default=None, description="URL the raw data was scraped from.")
    raw_description: str | None = Field(
        default=None,
        description="Complete scraped page content, copied directly before AI parsing. "
        "Includes requirements, pay, benefits, and other readable sections; not an AI rewrite.",
    )
    raw_payload: dict[str, JsonValue] | None = Field(
        default=None, description="Original scraped data, saved before AI parsing."
    )


ScrapeRunStatus = Literal["running", "completed", "not_modified", "failed"]


class ScrapeRunResponse(StrictModel):
    id: str
    source: str
    trigger: ScrapeTrigger | None = None
    status: ScrapeRunStatus
    started_at: float
    finished_at: float | None
    fetched: int
    matched: int
    created: int
    updated: int
    unchanged: int
    error: str | None
    performance: ScrapePerformance | None = None
    task_id: str | None = None
    phase: str | None = None
    items_done: int | None = Field(default=None, ge=0)
    items_total: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)

    elapsed_seconds: int = Field(default=0, ge=0)
    success: bool | None = None
    has_failures: bool = False

    @model_validator(mode="after")
    def derive_status(self) -> Self:
        self.elapsed_seconds = max(0, int((self.finished_at or time.time()) - self.started_at))
        self.has_failures = self.status == "failed" or bool(
            self.performance
            and (
                self.performance.failure_count
                or self.performance.page_failures
                or self.performance.ai_failures
            )
        )
        self.success = (
            None if self.status == "running" else self.status in {"completed", "not_modified"}
        )
        return self


@dataclass(kw_only=True)
class JobPageCache(StoredRecord):
    collection: ClassVar[str] = "job_page_cache"
    key_fields: ClassVar[tuple[str, ...]] = ("url_hash", "renderer_key")
    url_hash: str = ""
    renderer_key: str = ""
    requested_url: str = ""
    final_url: str = ""
    content: str = ""
    media_type: str = ""
    fetched_at: int = 0
    apply_url: str | None = None
    date_posted: int | None = None
    application_url: str | None = None


class JobPageSettings(StrictModel):
    max_age_days: int = Field(
        default=2, ge=0, le=365, description="Zero disables posting-age filtering"
    )
    renderer: Literal["http", "browser", "auto"] = "auto"
    http_concurrency: int = Field(default=6, ge=1, le=32)
    browser_concurrency: int = Field(default=2, ge=1, le=4)
    per_host_concurrency: int = Field(default=2, ge=1, le=8)
    cache_seconds: int = Field(default=86400, ge=0)
    cache_max_seconds: int = Field(default=7 * 86400, ge=0)
    max_downloads_per_scrape: int = Field(default=100, gt=0)
    max_page_bytes: int = Field(default=2 * 1024 * 1024, gt=0)
    timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    browser_channel: str | None = None
    browser_executable: str | None = None
    browser_headless: bool = True
    include_links: bool = False

    @model_validator(mode="after")
    def validate_browser_selection(self) -> Self:
        if self.browser_channel and self.browser_executable:
            raise ValueError("Set only one of JOB_BROWSER_CHANNEL and JOB_BROWSER_EXECUTABLE")
        return self

    @property
    def cache_key(self) -> str:
        value = [
            self.renderer,
            self.browser_channel if self.renderer != "http" else None,
            self.browser_executable if self.renderer != "http" else None,
            "full-job-pages-v6-complete-provider-html",
        ]
        if self.include_links:
            value.append("page-links-v1")
        if self.renderer != "http" and not self.browser_headless:
            value.append("visible-browser-v1")
        return hashlib.sha256(json.dumps(value).encode()).hexdigest()

    @classmethod
    def from_environment(cls) -> "JobPageSettings":
        load_environment()
        headless = os.environ.get("JOB_BROWSER_HEADLESS", "true").strip().lower()
        if headless not in {"true", "false", "1", "0"}:
            raise ValueError("JOB_BROWSER_HEADLESS must be true, false, 1, or 0")
        return cls.model_validate(
            {
                "max_age_days": int(os.environ.get("JOB_GITHUB_MAX_AGE_DAYS", "2")),
                "renderer": os.environ.get("JOB_PAGE_RENDERER", "auto"),
                "http_concurrency": int(os.environ.get("JOB_HTTP_CONCURRENCY", "6")),
                "browser_concurrency": int(os.environ.get("JOB_BROWSER_CONCURRENCY", "2")),
                "per_host_concurrency": int(os.environ.get("JOB_HOST_CONCURRENCY", "2")),
                "cache_seconds": int(os.environ.get("JOB_PAGE_CACHE_SECONDS", "86400")),
                "cache_max_seconds": int(
                    os.environ.get("JOB_PAGE_CACHE_MAX_SECONDS", str(7 * 86400))
                ),
                "max_downloads_per_scrape": int(os.environ.get("JOB_PAGE_MAX_DOWNLOADS", "100")),
                "max_page_bytes": int(os.environ.get("JOB_PAGE_MAX_BYTES", str(2 * 1024 * 1024))),
                "timeout_seconds": float(os.environ.get("JOB_PAGE_TIMEOUT_SECONDS", "30")),
                "browser_channel": os.environ.get("JOB_BROWSER_CHANNEL") or None,
                "browser_executable": os.environ.get("JOB_BROWSER_EXECUTABLE") or None,
                "browser_headless": headless in {"true", "1"},
            }
        )


@dataclass(kw_only=True)
class SharedExtraction(StoredRecord):
    collection: ClassVar[str] = "shared_extractions"
    key_fields: ClassVar[tuple[str, ...]] = ("fingerprint", "normalizer_key")
    fingerprint: str = ""
    normalizer_key: str = ""
    document: dict[str, JsonValue] = field(default_factory=dict[str, JsonValue])
    result: dict[str, JsonValue] = field(default_factory=dict[str, JsonValue])
    source: str = ""
    created_at: int = 0
