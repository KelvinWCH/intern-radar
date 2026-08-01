import argparse
from typing import Annotated, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator

from job_backend.common.models import StrictModel
from job_backend.scrape.utils.models import ScrapePacingSettings

SourceGroup = Literal["github", "boards", "companies"]
Timestamp = Annotated[float, Field(ge=0, allow_inf_nan=False)]
LocalHour = Annotated[int, Field(ge=0, le=23)]


class ScheduledScrape(StrictModel):
    group: SourceGroup
    interval_hours: float = Field(gt=0, le=168, allow_inf_nan=False)
    daily_hours: list[LocalHour] = Field(default_factory=list[int], max_length=24)
    enabled: bool = True
    # sources run side by side, each child still paces its own requests
    parallel_sources: int = Field(default=1, ge=1, le=4)
    max_source_seconds: float | None = Field(default=None, ge=1, le=86400, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_daily_hours(self) -> Self:
        if self.daily_hours:
            hours = self.daily_hours
            if hours != sorted(set(hours)):
                raise ValueError("daily_hours must be unique and sorted")
            gaps = [
                right - left for left, right in zip(hours, [*hours[1:], hours[0] + 24], strict=True)
            ]
            if any(gap != self.interval_hours for gap in gaps):
                raise ValueError("daily_hours must match interval_hours in local clock time")
        return self


class WorkerSettings(StrictModel):
    tasks: list[ScheduledScrape] = Field(min_length=1, max_length=4)
    timezone: str = "America/New_York"
    pacing: ScrapePacingSettings = Field(default_factory=ScrapePacingSettings)
    max_run_seconds: float = Field(default=7200.0, ge=1, le=86400, allow_inf_nan=False)
    max_source_seconds: float = Field(default=600.0, ge=1, le=86400, allow_inf_nan=False)
    shutdown_grace_seconds: float = Field(default=15.0, ge=1, le=120, allow_inf_nan=False)
    poll_seconds: float = Field(default=30.0, ge=1, le=60, allow_inf_nan=False)
    status_seconds: float = Field(default=15.0, ge=10, le=60, allow_inf_nan=False)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise ValueError("timezone must be a valid IANA timezone") from error
        return value

    @model_validator(mode="after")
    def validate_tasks(self) -> Self:
        if len({task.group for task in self.tasks}) != len(self.tasks):
            raise ValueError("Worker source groups must not be repeated")
        if not any(task.enabled for task in self.tasks):
            raise ValueError("Enable at least one worker task")
        return self


class WorkerState(StrictModel):
    version: Literal[1] = 1
    last_started: dict[SourceGroup, Timestamp] = Field(default_factory=dict[SourceGroup, float])
    schedule_started: dict[SourceGroup, Timestamp] = Field(default_factory=dict[SourceGroup, float])
    in_progress: dict[SourceGroup, Timestamp] = Field(default_factory=dict[SourceGroup, float])
    interrupted: dict[SourceGroup, Timestamp] = Field(default_factory=dict[SourceGroup, float])
    retry_at: dict[SourceGroup, Timestamp] = Field(default_factory=dict[SourceGroup, float])


class DailyMessageState(StrictModel):
    message_id: str | None = Field(default=None, pattern=r"^[0-9]+$")
    create_pending: bool = False
    part_ids: list[Annotated[str, Field(pattern=r"^[0-9]+$")]] = Field(default_factory=list)


class WorkerArguments(argparse.Namespace):
    once: bool
    show_schedule: bool
    check_browser: bool


class ScheduledScrapeControl(StrictModel):
    id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    group: SourceGroup
    started_at: float
    cancel_requested: bool = False
