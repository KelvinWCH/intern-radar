from dataclasses import dataclass, field
from typing import ClassVar, Literal

from pydantic import Field, JsonValue

from job_backend.common.models import StrictModel
from job_backend.jobs.models import ApplicationStatus
from job_backend.persistence.models import StoredRecord

ActivityKind = Literal[
    "job_added",
    "job_saved",
    "application_updated",
    "application_marked",
    "documents_generated",
    "resume_updated",
]


class ActivityData(StrictModel):
    schema_version: Literal[1] = 1
    job_id: str | None = Field(default=None, min_length=1)
    company: str | None = None
    title: str | None = None
    previous_status: ApplicationStatus | None = None
    status: ApplicationStatus | None = None
    document_id: str | None = None
    profile_revision: int | None = Field(default=None, ge=1)
    has_resume: bool = False
    has_cover_letter: bool = False
    backfilled: bool = False


class ActivityEvent(StrictModel):
    id: str
    kind: ActivityKind
    occurred_at: int = Field(ge=0)
    data: ActivityData


@dataclass(kw_only=True)
class ActivityRecord(StoredRecord):
    collection: ClassVar[str] = "activity_events"
    key_fields: ClassVar[tuple[str, ...]] = ("id",)
    id: str = ""
    kind: str = ""
    occurred_at: int = 0
    data: dict[str, JsonValue] = field(default_factory=dict[str, JsonValue])


class ActivityDay(StrictModel):
    date: str
    actions: int = 0
    applications: int = 0
    documents: int = 0
    resume_updates: int = 0


class PipelineStage(StrictModel):
    status: ApplicationStatus
    count: int


class ActivitySummary(StrictModel):
    start_date: str
    end_date: str
    generated_at: int
    total_applications: int
    active_days: int
    days: list[ActivityDay]
    pipeline: list[PipelineStage]
    recent: list[ActivityEvent]
