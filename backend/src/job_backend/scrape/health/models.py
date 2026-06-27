from typing import Literal

from pydantic import Field

from job_backend.common.models import StrictModel
from job_backend.scrape.worker.models import SourceGroup


class HealthReportState(StrictModel):
    day: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    reported: list[str] = Field(default_factory=list[str])


RegressionKind = Literal["failing", "collapsed", "stopped"]


class ScrapeRegression(StrictModel):
    kind: RegressionKind
    source: str | None
    group: SourceGroup
    since: float | None = None
    runs: int = Field(default=0, ge=0)
    last_worked: float | None = None
    fetched: int | None = None
    usual: int | None = None
    error: str | None = None

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.source or self.group}"


class ScrapeHealth(StrictModel):
    checked_at: float
    sources: int = Field(ge=0)
    healthy: int = Field(ge=0)
    regressions: list[ScrapeRegression] = Field(default_factory=list[ScrapeRegression])
