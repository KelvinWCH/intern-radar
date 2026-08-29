from dataclasses import dataclass

from pydantic import Field

from job_backend.common.models import StrictModel


@dataclass(frozen=True)
class PageSelector:
    tag: str | None = None
    attribute: str | None = None
    value: str | None = None
    ancestor_class: str | None = None
    prefix: bool = False
    excluded_ancestor_id: str | None = None


class PageFacts(StrictModel):
    title: str | None = None
    company_name: str | None = None
    locations: list[str] = Field(default_factory=list)
    source_job_id: str | None = None
    date_posted: str | None = None
    apply_url: str | None = None
    description: str | None = None
