import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Self

from pydantic import Field, model_validator

from job_backend.common.models import StrictModel


@dataclass(frozen=True)
class BrowserDocument:
    url: str
    html: str


@dataclass(frozen=True)
class BrowserReadOptions:
    max_page_bytes: int
    ready_selector: str | None = None
    wait_for_network_idle: bool = False
    wait_for_job_content: bool = False
    validate: Callable[[BrowserDocument], None] | None = None


class ScrapePacingSettings(StrictModel):
    min_delay_seconds: float = Field(default=2.0, ge=0, le=30, allow_inf_nan=False)
    max_delay_seconds: float = Field(default=5.0, ge=0, le=30, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.max_delay_seconds < self.min_delay_seconds:
            raise ValueError("max_delay_seconds must be at least min_delay_seconds")
        return self

    @classmethod
    def from_environment(cls) -> "ScrapePacingSettings":
        return cls(
            min_delay_seconds=float(os.environ.get("JOB_CRON_DELAY_MIN_SECONDS", "2")),
            max_delay_seconds=float(os.environ.get("JOB_CRON_DELAY_MAX_SECONDS", "5")),
        )
