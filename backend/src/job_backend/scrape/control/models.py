import time
from dataclasses import dataclass, field
from typing import Annotated, ClassVar, Literal

from pydantic import Field, JsonValue, StringConstraints, computed_field, field_validator

from job_backend.common.models import StrictModel
from job_backend.persistence.models import StoredRecord
from job_backend.scrape.control.constants import MAX_SELECTED_SOURCES
from job_backend.scrape.pipeline.models import ScrapeRunResponse
from job_backend.scrape.worker.models import ScheduledScrapeControl


class ScrapeSource(StrictModel):
    id: str
    name: str
    group: Literal["github", "company"]
    enabled: bool
    source_name: str | None
    reason: str | None = None


class ScrapeRequest(StrictModel):
    request_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )
    sources: list[str] = Field(min_length=1, max_length=MAX_SELECTED_SOURCES)
    max_runtime_seconds: int = Field(default=1800, ge=60, le=7200)
    use_ai: bool = False
    ai_model: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
        | None
    ) = None
    max_ai_calls: int = Field(default=100, ge=1, le=100)
    max_downloads: int = Field(default=100, ge=1, le=100)
    max_age_days: int = Field(default=2, ge=1, le=30)
    include_older_postings: bool = False

    @field_validator("sources")
    @classmethod
    def clean_terms(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 200 for value in values):
            raise ValueError("Selections must contain 1 to 200 characters")
        return list(dict.fromkeys(value.strip() for value in values))


@dataclass(kw_only=True)
class ScrapeTask(StoredRecord):
    collection: ClassVar[str] = "scrape_tasks"
    key_fields: ClassVar[tuple[str, ...]] = ("id",)
    id: str = ""
    settings: dict[str, JsonValue] = field(default_factory=dict[str, JsonValue])
    status: str = ""
    created_at: int = 0
    started_at: int | None = None
    finished_at: int | None = None
    cancel_requested: bool = False
    error: str | None = None


class ScrapeProgress(StrictModel):
    sources_total: int
    sources_finished: int
    current_source: str | None
    phase: str | None
    items_done: int | None
    items_total: int | None
    percent: int = Field(ge=0, le=100)


class ScrapeUsage(StrictModel):
    input_tokens: int
    output_tokens: int


class ScrapeEventResponse(StrictModel):
    id: str
    run_id: str
    created_at: float
    level: Literal["info", "warning", "error"]
    message: str


class ScrapeActivity(StrictModel):
    busy: bool
    runs: list[ScrapeRunResponse] = Field(default_factory=list[ScrapeRunResponse])
    events: list[ScrapeEventResponse] = Field(default_factory=list[ScrapeEventResponse])
    scheduled: ScheduledScrapeControl | None = None


class ScrapeTaskResponse(StrictModel):
    id: str
    settings: ScrapeRequest
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    created_at: int
    started_at: int | None
    finished_at: int | None
    cancel_requested: bool
    error: str | None
    runs: list[ScrapeRunResponse] = Field(default_factory=list[ScrapeRunResponse])
    events: list[ScrapeEventResponse] = Field(default_factory=list[ScrapeEventResponse])

    @computed_field
    @property
    def elapsed_seconds(self) -> int:
        return max(0, (self.finished_at or int(time.time())) - (self.started_at or self.created_at))

    @computed_field
    @property
    def usage(self) -> ScrapeUsage:
        return ScrapeUsage(
            input_tokens=sum(run.input_tokens or 0 for run in self.runs),
            output_tokens=sum(run.output_tokens or 0 for run in self.runs),
        )

    @computed_field
    @property
    def progress(self) -> ScrapeProgress:
        total = len(self.settings.sources)
        finished = min(total, sum(run.status != "running" for run in self.runs))
        current = next((run for run in reversed(self.runs) if run.status == "running"), None)
        fraction = (
            min(1.0, current.items_done / current.items_total)
            if current and current.items_done is not None and current.items_total
            else 0.0
        )
        percent = (
            100
            if self.status == "completed"
            else min(99, int(100 * (finished + fraction) / total))
            if total
            else 0
        )
        return ScrapeProgress(
            sources_total=total,
            sources_finished=finished,
            current_source=current.source if current else None,
            phase=current.phase if current else None,
            items_done=current.items_done if current else None,
            items_total=current.items_total if current else None,
            percent=percent,
        )


class ScrapeHistoryPage(StrictModel):
    items: list[ScrapeRunResponse]
    total: int | None
    limit: int
    offset: int
    next_cursor: str | None = None
