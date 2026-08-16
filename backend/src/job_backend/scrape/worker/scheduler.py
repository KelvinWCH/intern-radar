import time
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Protocol

from job_backend.common.logger import get_logger
from job_backend.scrape.worker.calendar import next_clock_time
from job_backend.scrape.worker.models import (
    ScheduledScrape,
    SourceGroup,
    WorkerSettings,
    WorkerState,
)
from job_backend.scrape.worker.state import save_state

logger = get_logger(__name__)

NETWORK_UNAVAILABLE = 3
# wait a bit before retrying when the internet was down
RETRY_SECONDS = 900.0


class IdleWork(Protocol):
    def __call__(self, *, after_batch: bool) -> None: ...


class ImportRunner(Protocol):
    def __call__(self, group: SourceGroup, /, *, resume_since: float | None = None) -> int: ...


def next_due(
    task: ScheduledScrape, state: WorkerState, timezone: str = "America/New_York"
) -> float:
    previous = state.last_started.get(task.group)
    if task.daily_hours:
        anchor = previous if previous is not None else state.schedule_started[task.group]
        due = next_clock_time(task.daily_hours, timezone, anchor, inclusive=previous is None)
    else:
        due = 0.0 if previous is None else previous + task.interval_hours * 3600
    retry = state.retry_at.get(task.group)
    return due if retry is None else min(due, retry)


def run_schedule(
    settings: WorkerSettings,
    state: WorkerState,
    state_path: Path,
    stop: Event,
    run: ImportRunner,
    *,
    once: bool = False,
    clock: Callable[[], float] = time.time,
    live_status: bool = False,
    idle: IdleWork | None = None,
) -> int:
    completed: set[SourceGroup] = set()
    failed = False
    initialized = False
    for task in settings.tasks:
        if task.enabled and task.daily_hours and task.group not in state.schedule_started:
            state.schedule_started[task.group] = clock()
            initialized = True
    for task in settings.tasks:
        started_at = state.in_progress.get(task.group)
        if task.enabled and started_at is not None:
            state.interrupted.setdefault(task.group, started_at)
            state.retry_at[task.group] = clock()
            del state.in_progress[task.group]
            initialized = True
            logger.info("Resuming the interrupted %s import", task.group)
    if initialized:
        save_state(state_path, state)
    while not stop.is_set():
        tasks = [
            task
            for task in settings.tasks
            if task.enabled and (not once or task.group not in completed)
        ]
        if not tasks:
            break
        task = min(tasks, key=lambda item: next_due(item, state, settings.timezone))
        now = clock()
        wait = next_due(task, state, settings.timezone) - now
        if wait > 0:
            if once:
                break
            if idle is not None:
                idle(after_batch=False)
                wait = next_due(task, state, settings.timezone) - clock()
                if wait <= 0:
                    continue
            stop.wait(min(wait, settings.poll_seconds))
            continue
        state.last_started[task.group] = now
        state.in_progress[task.group] = now
        resume_since = state.interrupted.get(task.group)
        save_state(state_path, state)
        logger.info(
            "Starting scheduled %s import (every %s hours)",
            task.group,
            task.interval_hours,
            extra={
                "discord_scrape": not live_status,
                "context": {
                    "event": "started",
                    "group": task.group,
                    "interval_hours": task.interval_hours,
                },
            },
        )
        started = time.monotonic()
        try:
            code = run(task.group, resume_since=resume_since)
        except Exception:
            logger.exception("Could not run %s importer; continuing the schedule", task.group)
            code = 1
        completed.add(task.group)
        failed = failed or code != 0
        if code == NETWORK_UNAVAILABLE:
            state.interrupted.setdefault(task.group, now)
            state.retry_at[task.group] = clock() + RETRY_SECONDS
            del state.in_progress[task.group]
        elif code == 130 and stop.is_set():
            pass
        else:
            state.in_progress.pop(task.group, None)
            state.interrupted.pop(task.group, None)
            state.retry_at.pop(task.group, None)
        save_state(state_path, state)
        event = {0: "completed", 124: "timeout", 130: "cancelled"}.get(code, "failed")
        extra = {
            "discord_scrape": not live_status,
            "context": {
                "event": event,
                "group": task.group,
                "exit_code": code,
                "duration_seconds": round(time.monotonic() - started, 1),
                "interval_hours": task.interval_hours,
            },
        }
        if code == 0:
            logger.info("Scheduled %s import completed", task.group, extra=extra)
        elif code == NETWORK_UNAVAILABLE:
            logger.warning(
                "Scheduled %s import could not reach the internet; retrying in %s minutes",
                task.group,
                round(RETRY_SECONDS / 60),
                extra=extra,
            )
        else:
            logger.warning(
                "Scheduled %s import exited with code %s; next attempt follows its schedule",
                task.group,
                code,
                extra=extra,
            )
        if idle is not None and not stop.is_set():
            idle(after_batch=True)
    return int(failed) if once else 0
