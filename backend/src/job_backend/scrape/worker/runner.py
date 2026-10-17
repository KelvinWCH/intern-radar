import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Literal

from filelock import Timeout
from pydantic import SecretStr

from job_backend.common.logger import get_logger
from job_backend.common.models import DailyJobsTarget
from job_backend.persistence.database import Database, make_engine, migrate
from job_backend.persistence.session import Session
from job_backend.scrape.companies.companies import COMPANIES
from job_backend.scrape.companies.company_sources import COMPANY_SOURCES
from job_backend.scrape.daily_notifications import publish_daily_jobs
from job_backend.scrape.models import ScrapeRun
from job_backend.scrape.utils.constants import UNATTENDED_BROWSER_ENV
from job_backend.scrape.utils.source_skips import SKIPPED_PHASES
from job_backend.scrape.worker.constants import GROUP_ARGUMENTS
from job_backend.scrape.worker.control import read_scheduled_scrape, scheduled_scrape_control
from job_backend.scrape.worker.live_status import LiveStatus
from job_backend.scrape.worker.models import SourceGroup, WorkerSettings
from job_backend.scrape.worker.ownership import scrape_execution_lock
from job_backend.scrape.worker.recovery import (
    finish_stopped_source,
    recover_interrupted_scrape_runs,
)
from job_backend.scrape.worker.sources import group_sources

logger = get_logger(__name__)

SUPERVISED_ENV = "JOB_SCRAPE_SUPERVISED"
NETWORK_UNAVAILABLE = 3
TRANSIENT_FAILURE = re.compile(
    r"^(?:ConnectError|ConnectTimeout|ReadTimeout|WriteTimeout|PoolTimeout|ReadError|"
    r"RemoteProtocolError)\b|scheduled maintenance|Server error '5\d\d"
)
RETRY_PAUSE_SECONDS = 30.0


def finished_sources(engine: Database, since: float) -> set[str]:
    with Session(engine, read_only=True) as session:
        return {
            run.source
            for run in session.find(
                ScrapeRun, equal={"trigger": "cron"}, interval=("started_at", since, None)
            )
            if run.status in {"completed", "not_modified"}
        }


def internet_unreachable(engine: Database, since: float) -> bool:
    with Session(engine, read_only=True) as session:
        runs = list(
            session.find(ScrapeRun, equal={"trigger": "cron"}, interval=("started_at", since, None))
        )
    return len(runs) >= 2 and all(
        run.status == "failed" and run.phase in SKIPPED_PHASES for run in runs
    )


def transient_failures(engine: Database, since: float) -> set[str]:
    with Session(engine, read_only=True) as session:
        runs = session.find(
            ScrapeRun, equal={"trigger": "cron"}, interval=("started_at", since, None)
        )
        ordered = sorted(runs, key=lambda run: run.started_at)
    latest = {run.source: run for run in ordered}
    return {
        source
        for source, run in latest.items()
        if run.status == "failed" and run.error and TRANSIENT_FAILURE.search(run.error)
    }


def build_scrape_commands(group: SourceGroup, database: Path) -> list[tuple[str, list[str]]]:
    flag = GROUP_ARGUMENTS[group]
    command = [
        sys.executable,
        "-m",
        "job_backend.cli",
        "--unattended",
        "--trigger",
        "cron",
        "--state-path",
        str(database),
    ]
    return [(name, [*command, flag, key]) for key, name in group_sources(group)]


def source_lanes(group: SourceGroup) -> dict[str, str]:
    if group not in {"boards", "companies"}:
        return {}
    lanes: dict[str, str] = {}
    for key, source in COMPANY_SOURCES.items():
        lanes[source.name] = COMPANIES[key].job_board
    return lanes


def stop_scrape_process(process: subprocess.Popen[bytes], grace_seconds: float) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=grace_seconds,
            )
        except (OSError, subprocess.SubprocessError):
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait()
    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


@dataclass
class _Child:
    name: str
    process: subprocess.Popen[bytes]
    started_at: float
    deadline: float


class _Supervisor:
    def __init__(
        self,
        group: SourceGroup,
        database: Path,
        settings: WorkerSettings,
        stop: Event,
        status: LiveStatus | None,
        engine: Database,
        environment: dict[str, str],
        status_seconds: float,
        resume_since: float | None = None,
    ) -> None:
        self.group: SourceGroup = group
        self.database = database
        self.settings = settings
        self.stop = stop
        self.status = status
        self.engine = engine
        self.environment = environment
        self.status_seconds = status_seconds
        task = next((item for item in settings.tasks if item.group == group), None)
        self.parallel = task.parallel_sources if task is not None else 1
        self.source_seconds = (
            task.max_source_seconds
            if task is not None and task.max_source_seconds is not None
            else settings.max_source_seconds
        )
        self.lanes = source_lanes(group)
        self.pending = build_scrape_commands(group, database)
        if resume_since is not None:
            finished = finished_sources(engine, resume_since)
            self.pending = [item for item in self.pending if item[0] not in finished]
            message = (
                f"Resuming the {group} import: {len(finished)} sources finished before the "
                f"interruption, {len(self.pending)} remain"
            )
            logger.info(message)
            if status is not None:
                status.record_warning(message)
        self.running: list[_Child] = []
        self.started_at = time.time()
        self.code = 0
        self.halted = False
        self.retried = False

    def run(self) -> int:
        group_deadline = time.monotonic() + self.settings.max_run_seconds
        next_update = time.monotonic() + self.status_seconds
        try:
            while True:
                self._supervise(group_deadline, next_update)
                if self.code in {124, 130} or self.halted or not self._queue_retries():
                    break
            if self.code == 0 and internet_unreachable(self.engine, self.started_at):
                self._error(
                    f"No {self.group} source could be reached; the import is retried soon",
                    code=NETWORK_UNAVAILABLE,
                )
            return self.code
        finally:
            self._stop_all(
                "interrupted", reason="Scheduled import stopped before this source finished."
            )

    def _supervise(self, group_deadline: float, next_update: float) -> None:
        while self.pending or self.running:
            self._launch()
            if not self.running:
                break
            soonest = min([group_deadline, *(child.deadline for child in self.running)])
            self.stop.wait(min(1.0, max(0.0, soonest - time.monotonic())))
            control = read_scheduled_scrape(self.database)
            if self.stop.is_set() or (control is not None and control.cancel_requested):
                reason = (
                    "Scheduled import cancelled by worker shutdown."
                    if self.stop.is_set()
                    else "Scheduled import stopped from the frontend. "
                    "Completed source imports are preserved."
                )
                self.code = 130
                self._stop_all("interrupted", reason=reason)
                break
            if time.monotonic() >= group_deadline:
                self._warn(
                    f"Scheduled {self.group} import reached its "
                    f"{self.settings.max_run_seconds:g} second limit; remaining sources "
                    "wait for the next run"
                )
                self.code = 124
                self._stop_all("timeout")
                break
            self._reap()
            if self.status is not None and time.monotonic() >= next_update:
                self.status.update()
                next_update = time.monotonic() + self.status_seconds

    def _queue_retries(self) -> bool:
        if self.retried or internet_unreachable(self.engine, self.started_at):
            return False
        self.retried = True
        failed = transient_failures(self.engine, self.started_at)
        self.pending = [
            item for item in build_scrape_commands(self.group, self.database) if item[0] in failed
        ]
        if not self.pending:
            return False
        self._warn(
            f"Retrying {len(self.pending)} {self.group} source"
            f"{'s' if len(self.pending) != 1 else ''} after a brief network or site problem: "
            + ", ".join(name for name, _command in self.pending)
        )
        self.stop.wait(RETRY_PAUSE_SECONDS)
        return not self.stop.is_set()

    def _launch(self) -> None:
        while self.pending and len(self.running) < self.parallel and not self.halted:
            active = {self.lanes.get(child.name, child.name) for child in self.running}
            index = next(
                (
                    position
                    for position, (name, _command) in enumerate(self.pending)
                    if self.lanes.get(name, name) not in active
                ),
                0,
            )
            name, command = self.pending.pop(index)
            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    env=self.environment,
                    start_new_session=os.name != "nt",
                )
            except OSError as error:
                logger.exception("Could not start scheduled source %s", name)
                if self.status is not None:
                    self.status.record_error(f"{name}: {error}")
                if self.code == 0:
                    self.code = 1
                continue
            self.running.append(
                _Child(
                    name,
                    process,
                    time.time(),
                    time.monotonic() + self.source_seconds,
                )
            )

    def _reap(self) -> None:
        for child in list(self.running):
            polled = child.process.poll()
            if polled is not None:
                self.running.remove(child)
                # the importer can leave a browser behind so kill the whole group
                stop_scrape_process(child.process, self.settings.shutdown_grace_seconds)
                if self.code == 0:
                    self.code = polled
                if polled == 2:
                    self.halted = True
            elif time.monotonic() >= child.deadline:
                self.running.remove(child)
                reason = (
                    f"Skipped {child.name} until the next run: source took over "
                    f"{self.source_seconds:g} seconds."
                )
                self._warn(reason)
                self._finish(child, reason, "timeout")

    def _stop_all(
        self, phase: Literal["timeout", "interrupted"], *, reason: str | None = None
    ) -> None:
        children, self.running = self.running, []
        for child in children:
            if reason is None:
                skipped = (
                    f"Skipped {child.name} until the next run: category {self.group} reached "
                    f"{self.settings.max_run_seconds:g} seconds."
                )
                self._warn(skipped)
                self._finish(child, skipped, phase)
            else:
                self._finish(child, reason, phase)

    def _finish(self, child: _Child, reason: str, phase: Literal["timeout", "interrupted"]) -> None:
        try:
            stop_scrape_process(child.process, self.settings.shutdown_grace_seconds)
        finally:
            finish_stopped_source(
                self.database,
                child.name,
                child.started_at,
                reason,
                phase=phase,
                engine=self.engine,
            )

    def _warn(self, message: str) -> None:
        logger.warning(message)
        if self.status is not None:
            self.status.record_warning(message)

    def _error(self, message: str, *, code: int = 1) -> None:
        logger.error(message)
        if self.status is not None:
            self.status.record_error(message)
        if self.code == 0:
            self.code = code


def run_scrape_process(
    group: SourceGroup,
    database: Path,
    settings: WorkerSettings,
    stop: Event,
    *,
    webhook: SecretStr | None = None,
    daily: DailyJobsTarget | None = None,
    status_seconds: float = 15.0,
    resume_since: float | None = None,
) -> int:
    environment = {
        **os.environ,
        **UNATTENDED_BROWSER_ENV,
        "JOB_CRON_DELAY_MIN_SECONDS": str(settings.pacing.min_delay_seconds),
        "JOB_CRON_DELAY_MAX_SECONDS": str(settings.pacing.max_delay_seconds),
        SUPERVISED_ENV: "1",
    }
    status = LiveStatus(webhook, database, group) if webhook is not None else None
    started_at = time.time()
    if daily is not None:
        environment["JOB_DISCORD_DAILY_SUPERVISED"] = "1"
    if status is not None:
        environment["JOB_DISCORD_LIVE_STATUS"] = "1"
        status.start()
    code = 0
    engine: Database | None = None
    try:
        with scheduled_scrape_control(database, group), scrape_execution_lock(database):
            engine = make_engine(database)
            migrate(engine)
            recover_interrupted_scrape_runs(engine)
            code = _Supervisor(
                group,
                database,
                settings,
                stop,
                status,
                engine,
                environment,
                status_seconds,
                resume_since=resume_since,
            ).run()
        return code
    except Timeout:
        message = (
            f"Another importer is already running; the scheduled {group} import "
            "waits for the next schedule."
        )
        logger.warning(message)
        if status is not None:
            status.record_warning(message)
        code = 2
        return code
    except Exception as error:
        if code == 0:
            code = 1
        if status is not None:
            status.record_error(f"Could not run {group} importer: {error}")
        raise
    finally:
        try:
            if status is not None:
                status.finish(code)
        finally:
            if engine is not None:
                engine.dispose()
            publish_daily_jobs(
                daily,
                database,
                started_at,
                time.time(),
                create=not stop.is_set(),
            )
