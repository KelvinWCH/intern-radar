from collections import defaultdict
from dataclasses import dataclass
from statistics import median

from job_backend.persistence.models import Document, Filter, Junction, Order, ReadQuery
from job_backend.persistence.session import Session
from job_backend.scrape.health.constants import (
    COLLAPSE_MIN_BASELINE,
    COLLAPSE_MIN_USUAL,
    COLLAPSE_SHARE,
    ERROR_CHARACTERS,
    FAILING_STREAK,
    HISTORY_SECONDS,
    RECENT_SECONDS,
    STOPPED_INTERVALS,
    STOPPED_MIN_SECONDS,
)
from job_backend.scrape.health.models import ScrapeHealth, ScrapeRegression
from job_backend.scrape.worker.models import ScheduledScrape

_PAGE = 1000
_WORKED = frozenset({"completed", "not_modified"})


@dataclass(frozen=True)
class _Run:
    status: str
    started_at: float
    finished_at: float
    fetched: int
    error: str | None


def _run(row: Document) -> _Run | None:
    status = row.get("status")
    started = row.get("started_at")
    finished = row.get("finished_at")
    fetched = row.get("fetched")
    error = row.get("error")
    if (
        status not in {*_WORKED, "failed"}
        or row.get("phase") == "interrupted"
        or not isinstance(started, int | float)
        or not isinstance(finished, int | float)
    ):
        return None
    return _Run(
        status=str(status),
        started_at=float(started),
        finished_at=float(finished),
        fetched=fetched if isinstance(fetched, int) else 0,
        error=error if isinstance(error, str) and error else None,
    )


def _history(session: Session, since: float) -> dict[str, list[_Run]]:
    query = ReadQuery(
        "import_runs",
        Junction((Filter("trigger", value="cron"), Filter("started_at", "ge", since))),
        order=(Order("started_at", numeric=True),),
        fields=("source", "status", "phase", "started_at", "finished_at", "fetched", "error"),
    )
    runs: dict[str, list[_Run]] = defaultdict(list)
    offset = 0
    while True:
        rows = session.select(query, limit=_PAGE, offset=offset, count=False).items
        for row in rows:
            source = row.get("source")
            run = _run(row)
            if isinstance(source, str) and run is not None:
                runs[source].append(run)
        if len(rows) < _PAGE:
            break
        offset += _PAGE
    for source_runs in runs.values():
        source_runs.sort(key=lambda run: run.started_at)
    return runs


def _stopped_after(task: ScheduledScrape) -> float:
    return max(task.interval_hours * 3600 * STOPPED_INTERVALS, STOPPED_MIN_SECONDS)


def _failing(source: str, task: ScheduledScrape, runs: list[_Run]) -> ScrapeRegression | None:
    streak = 0
    for run in reversed(runs):
        if run.status != "failed":
            break
        streak += 1
    if not streak:
        return None
    window = task.interval_hours * 3600 / 2
    attempts = 1
    attempt_started = runs[-streak].started_at
    for run in runs[-streak + 1 :] if streak > 1 else []:
        if run.started_at - attempt_started >= window:
            attempts += 1
            attempt_started = run.started_at
    if attempts < FAILING_STREAK:
        return None
    worked = runs[-streak - 1] if streak < len(runs) else None
    error = runs[-1].error
    return ScrapeRegression(
        kind="failing",
        source=source,
        group=task.group,
        since=runs[-streak].started_at,
        runs=attempts,
        last_worked=worked.finished_at if worked is not None else None,
        error=error[:ERROR_CHARACTERS] if error else None,
    )


def _collapsed(
    source: str, task: ScheduledScrape, runs: list[_Run], recent_since: float
) -> ScrapeRegression | None:
    completed = [run for run in runs if run.status == "completed"]
    recent = [run for run in completed if run.started_at >= recent_since]
    earlier = [run.fetched for run in completed if run.started_at < recent_since]
    if not recent or len(earlier) < COLLAPSE_MIN_BASELINE:
        return None
    usual = median(earlier)
    most = max(run.fetched for run in recent)
    if usual < COLLAPSE_MIN_USUAL or most >= usual * COLLAPSE_SHARE:
        return None
    return ScrapeRegression(
        kind="collapsed",
        source=source,
        group=task.group,
        since=recent[0].started_at,
        fetched=most,
        usual=round(usual),
    )


def scrape_health(
    session: Session, scheduled: dict[str, ScheduledScrape], now: float
) -> ScrapeHealth:
    history = _history(session, now - HISTORY_SECONDS)
    groups: dict[str, list[str]] = defaultdict(list)
    for source, task in scheduled.items():
        groups[task.group].append(source)
    stopped_groups: list[ScrapeRegression] = []
    findings: list[ScrapeRegression] = []
    unhealthy = 0
    for sources in groups.values():
        task = scheduled[sources[0]]
        limit = now - _stopped_after(task)
        finished = [history[source][-1].finished_at for source in sources if history[source]]
        last = max(finished, default=None)
        if last is None or last < limit:
            stopped_groups.append(
                ScrapeRegression(kind="stopped", source=None, group=task.group, since=last)
            )
            unhealthy += len(sources)
            continue
        for source in sources:
            runs = history[source]
            if not runs:
                continue
            finding = (
                ScrapeRegression(
                    kind="stopped", source=source, group=task.group, since=runs[-1].finished_at
                )
                if runs[-1].finished_at < limit
                else _failing(source, task, runs)
                or _collapsed(source, task, runs, now - RECENT_SECONDS)
            )
            if finding is not None:
                findings.append(finding)
                unhealthy += 1
    order = {"failing": 0, "collapsed": 1, "stopped": 2}
    findings.sort(key=lambda finding: order[finding.kind])
    return ScrapeHealth(
        checked_at=now,
        sources=len(scheduled),
        healthy=len(scheduled) - unhealthy,
        regressions=[*stopped_groups, *findings],
    )
