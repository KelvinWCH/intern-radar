import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import Field, JsonValue

from job_backend.common.models import StrictModel
from job_backend.persistence.models import StoredRecord


class JobReportItem(StrictModel):
    id: str
    company: str
    title: str
    locations: list[str]
    terms: list[str]
    application_url: str | None
    apply_url: str | None
    date_posted: int | None
    first_seen_at: int
    is_toronto_area: bool | None


FailureStage = Literal["setup", "discovery", "download", "extraction", "persistence"]


class ScrapeFailure(StrictModel):
    stage: FailureStage
    error_type: str
    reason: str
    url: str | None = None


class ScrapePerformance(StrictModel):
    elapsed_seconds: float = Field(default=0, ge=0)
    discovery_seconds: float = Field(default=0, ge=0)
    download_seconds: float = Field(default=0, ge=0)
    ai_seconds: float = Field(default=0, ge=0)
    persistence_seconds: float = Field(default=0, ge=0)
    downloads: int = Field(default=0, ge=0)
    page_cache_hits: int = Field(default=0, ge=0)
    page_failures: int = Field(default=0, ge=0)
    browser_reads: int = Field(default=0, ge=0)
    browser_fallbacks: int = Field(default=0, ge=0)
    ai_calls: int = Field(default=0, ge=0)
    ai_cache_hits: int = Field(default=0, ge=0)
    shared_cache_hits: int = Field(default=0, ge=0)
    ai_failures: int = Field(default=0, ge=0)
    documents: int = Field(default=0, ge=0)
    jobs_per_minute: float = Field(default=0, ge=0)
    failure_count: int = Field(default=0, ge=0)
    failures: list[ScrapeFailure] = Field(default_factory=list[ScrapeFailure], max_length=100)
    failures_omitted: int = Field(default=0, ge=0)


ScrapeTrigger = Literal["manual", "cron", "cli"]


@dataclass(kw_only=True)
class ScrapeEvent(StoredRecord):
    collection: ClassVar[str] = "scrape_events"
    key_fields: ClassVar[tuple[str, ...]] = ("id",)
    id: str = ""
    run_id: str = ""
    task_id: str | None = None
    created_at: float = 0.0
    level: str = ""
    message: str = ""


@dataclass(kw_only=True)
class ScrapeRun(StoredRecord):
    collection: ClassVar[str] = "import_runs"
    key_fields: ClassVar[tuple[str, ...]] = ("id",)
    id: str = ""
    source: str = ""
    trigger: str | None = None
    status: str = ""
    started_at: float = 0.0
    finished_at: float | None = None
    fetched: int = 0
    matched: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    error: str | None = None
    task_id: str | None = None
    phase: str | None = None
    items_done: int | None = None
    items_total: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    performance: dict[str, JsonValue] | None = None


class ScrapeSummary(StrictModel):
    created: int = Field(ge=0)
    duplicates: int = Field(ge=0, description="Existing unchanged job encounters, not unique jobs.")
    updated: int = Field(ge=0)
    runs: int = Field(ge=0)
    failed_runs: int = Field(ge=0)
    running_runs: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    scrape_seconds: int = Field(ge=0, description="Summed wall time of the counted attempts.")


@dataclass(kw_only=True)
class SourceState(StoredRecord):
    collection: ClassVar[str] = "source_states"
    key_fields: ClassVar[tuple[str, ...]] = ("source",)
    source: str = ""
    etag: str | None = None
    normalizer_key: str | None = None
    missing_since: dict[str, int] = field(default_factory=dict[str, int])


class ScrapeArguments(argparse.Namespace):
    database: Path
    repositories: list[str] | None
    all_repositories: bool
    companies: list[str] | None
    all_companies: bool
    list_companies: bool
    unattended: bool
    trigger: ScrapeTrigger
    use_ai: bool
