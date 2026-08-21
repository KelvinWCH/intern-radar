from datetime import datetime
from zoneinfo import ZoneInfo

from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.scrape.health.models import ScrapeHealth, ScrapeRegression
from job_backend.scrape.health.regressions import scrape_health
from job_backend.scrape.models import ScrapeRun
from job_backend.scrape.worker.models import ScheduledScrape

HOUR = 3600.0
ZONE = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 27, 9, 30, tzinfo=ZONE).timestamp()
BOARDS = ScheduledScrape(group="boards", interval_hours=3)
COMPANIES = ScheduledScrape(group="companies", interval_hours=12, daily_hours=[3, 15])
NOT_FOUND = (
    "HTTPStatusError: Client error '404 Not Found' for url "
    "'https://boards-api.greenhouse.io/v1/boards/example/jobs'"
)


def _run(
    source: str,
    hours_ago: float,
    status: str = "completed",
    *,
    fetched: int = 40,
    error: str | None = None,
    trigger: str = "cron",
    phase: str | None = None,
) -> ScrapeRun:
    started = NOW - hours_ago * HOUR
    return ScrapeRun(
        id=f"{source}-{trigger}-{hours_ago}",
        source=source,
        trigger=trigger,
        status=status,
        started_at=started,
        finished_at=started + 60,
        fetched=fetched,
        error=error,
        phase=phase or ("skipped" if status == "failed" else "finished"),
    )


def _every(
    source: str,
    start: float,
    stop: float,
    status: str = "completed",
    *,
    step: float = 3,
    fetched: int = 40,
    error: str | None = None,
) -> list[ScrapeRun]:
    runs: list[ScrapeRun] = []
    hours = start
    while hours > stop:
        runs.append(_run(source, hours, status, fetched=fetched, error=error))
        hours -= step
    return runs


def _save(engine: Database, runs: list[ScrapeRun]) -> None:
    with Session(engine) as session, session.begin():
        for run in runs:
            session.add(run)


def _health(engine: Database, scheduled: dict[str, ScheduledScrape]) -> ScrapeHealth:
    with Session(engine, read_only=True) as session:
        return scrape_health(session, scheduled, NOW)


def test_failing_streak(
    engine: Database,
) -> None:
    _save(
        engine,
        [
            *_every("steady", 160, 0),
            *_every("broken", 160, 30),
            *_every("broken", 30, 0, "failed", error=NOT_FOUND),
            *_every("flaky", 160, 2),
            _run("flaky", 1, "failed", error="ReadTimeout: timed out"),
            *_every("restarted", 160, 2),
            _run("restarted", 1, "failed", error="Interrupted", phase="interrupted"),
            _run("restarted", 0.5, "failed", error="Interrupted", phase="interrupted"),
            *_every("manual", 160, 0),
            _run("manual", 2, "failed", error=NOT_FOUND, trigger="manual"),
            _run("manual", 1, "failed", error=NOT_FOUND, trigger="manual"),
            *_every("retried", 160, 2),
            _run("retried", 1.5, "failed", error="ReadTimeout: timed out"),
            _run("retried", 1, "failed", error="ReadTimeout: timed out"),
            *_every("outage", 160, 2),
            *_every("outage", 1.25, 0, "failed", step=0.25, error="ConnectError: unreachable"),
        ],
    )
    sources = ("steady", "broken", "flaky", "restarted", "manual", "retried", "outage")
    health = _health(engine, dict.fromkeys(sources, BOARDS))
    assert (health.sources, health.healthy) == (7, 6)
    assert health.regressions == [
        ScrapeRegression(
            kind="failing",
            source="broken",
            group="boards",
            since=NOW - 30 * HOUR,
            runs=10,
            last_worked=NOW - 31 * HOUR + 60,
            error=NOT_FOUND,
        )
    ]


def test_stopped_sources(engine: Database) -> None:
    _save(
        engine,
        [
            *_every("running", 160, 0),
            *_every("dropped", 160, 48),
            *_every("company-a", 160, 72, step=12),
            *_every("company-b", 160, 72, step=12),
        ],
    )
    scheduled = {
        "running": BOARDS,
        "dropped": BOARDS,
        "brand-new": BOARDS,
        "company-a": COMPANIES,
        "company-b": COMPANIES,
    }
    health = _health(engine, scheduled)
    assert (health.sources, health.healthy) == (5, 2)
    assert [(finding.kind, finding.source, finding.group) for finding in health.regressions] == [
        ("stopped", None, "companies"),
        ("stopped", "dropped", "boards"),
    ]
    assert health.regressions[0].since == NOW - 76 * HOUR + 60
