import os
import subprocess
import time
from pathlib import Path
from threading import Event, Lock, Thread

from filelock import Timeout
from pydantic import JsonValue, TypeAdapter

from job_backend.persistence.database import Database
from job_backend.persistence.errors import ConflictError
from job_backend.persistence.session import Session
from job_backend.scrape.control.catalog import build_scrape_command
from job_backend.scrape.control.models import (
    ScrapeEventResponse,
    ScrapeRequest,
    ScrapeTask,
    ScrapeTaskResponse,
)
from job_backend.scrape.models import ScrapeEvent, ScrapeRun
from job_backend.scrape.pipeline.models import ScrapeRunResponse
from job_backend.scrape.worker.ownership import process_lock, scrape_execution_lock
from job_backend.scrape.worker.runner import stop_scrape_process


class ScrapeBusyError(ValueError):
    pass


def task_response(
    session: Session,
    task: ScrapeTask,
    *,
    events: bool = False,
    runs: list[ScrapeRun] | None = None,
) -> ScrapeTaskResponse:
    result = ScrapeTaskResponse.model_validate(task)
    if runs is None:
        runs = session.find(
            ScrapeRun,
            equal={"task_id": task.id},
            order_by=("started_at", "id"),
        )
    result.runs = [ScrapeRunResponse.model_validate(run) for run in runs]
    if events:
        latest = session.filtered_recent(
            ScrapeEvent,
            "created_at",
            limit=80,
            equal={"task_id": task.id},
        )
        result.events = [ScrapeEventResponse.model_validate(event) for event in latest][::-1]
    return result


class ScrapeController:
    def __init__(self, engine: Database) -> None:
        self.engine = engine
        self.database = Path(str(engine.local_path))
        self.lock = process_lock(self.database, "ui-scrape")
        self.stop = Event()
        self.thread: Thread | None = None
        self.recovery_thread: Thread | None = None
        self.start_lock = Lock()

    def recover(self) -> None:
        if self._recover_once():
            return
        if self.recovery_thread is None or not self.recovery_thread.is_alive():
            self.recovery_thread = Thread(
                target=self._wait_for_recovery, daemon=True, name="job-workspace-recovery"
            )
            self.recovery_thread.start()

    def _wait_for_recovery(self) -> None:
        while not self.stop.wait(1):
            if self._recover_once():
                return

    def _recover_once(self) -> bool:
        try:
            with process_lock(self.database, "ui-scrape"), scrape_execution_lock(self.database):
                with (
                    Session(self.engine) as session,
                    session.begin(),
                ):
                    tasks = session.match_any(ScrapeTask, "status", {"queued", "running"})
                    ids = {task.id for task in tasks}
                    now = int(time.time())
                    for row in tasks:
                        row.status = "failed"
                        row.finished_at = now
                        row.error = "API restarted before this scrape finished. Retry the run."
                    runs: list[ScrapeRun] = (
                        session.find(
                            ScrapeRun,
                            equal={"status": "running"},
                            where=lambda row: row.task_id in ids,
                        )
                        if ids
                        else []
                    )
                    for row in runs:
                        row.status = "failed"
                        row.finished_at = now
                        row.phase = "interrupted"
                        row.error = "API restarted during this source import."
        except Timeout:
            return False
        return True

    def start(self, request: ScrapeRequest) -> ScrapeTaskResponse:
        with self.start_lock:
            return self._start(request)

    def _start(self, request: ScrapeRequest) -> ScrapeTaskResponse:
        command = build_scrape_command(request, self.database)
        with Session(self.engine) as session:
            existing = session.get(ScrapeTask, request.request_id)
            if existing:
                return task_response(session, existing, events=True)
        if self.thread is not None and self.thread.is_alive():
            raise ScrapeBusyError("A scrape is already running. Wait or cancel it first.")
        try:
            self.lock.acquire()
        except Timeout:
            raise ScrapeBusyError("A scrape is already running in another API process.") from None
        try:
            with scrape_execution_lock(self.database):
                pass
            with (
                Session(self.engine) as session,
                session.begin(),
            ):
                task = ScrapeTask(
                    id=request.request_id,
                    settings=TypeAdapter(dict[str, JsonValue]).validate_python(
                        request.model_dump(mode="json")
                    ),
                    status="queued",
                    created_at=int(time.time()),
                    cancel_requested=False,
                )
                session.add(task)
                session.flush()
                result = ScrapeTaskResponse.model_validate(task)
            self.thread = Thread(
                target=self._run, args=(request, command), daemon=True, name="job-workspace-scrape"
            )
            self.thread.start()
            return result
        except Timeout:
            self.lock.release()
            raise ScrapeBusyError("Another importer is running. Wait until it finishes.") from None
        except Exception:
            self.lock.release()
            raise

    def close(self) -> None:
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=10)
        if self.recovery_thread:
            self.recovery_thread.join(timeout=2)

    def _run(self, request: ScrapeRequest, command: list[str]) -> None:
        status = "failed"
        error: str | None = None
        environment = {
            **os.environ,
            **(
                {"JOB_DATABASE_URL": self.engine.connection_url}
                if self.engine.connection_url
                else {}
            ),
            "JOB_SCRAPE_TASK_ID": request.request_id,
            "JOB_AI_MAX_CALLS_PER_IMPORT": str(request.max_ai_calls),
            "JOB_PAGE_MAX_DOWNLOADS": str(request.max_downloads),
            "JOB_GITHUB_MAX_AGE_DAYS": str(
                0 if request.include_older_postings else request.max_age_days
            ),
        }
        if request.use_ai and request.ai_model:
            environment["JOB_AI_MODEL"] = request.ai_model
        try:
            with (
                Session(self.engine) as session,
                session.begin(),
            ):
                row = session.get(ScrapeTask, request.request_id)
                if row is not None:
                    row.status = "running"
                    row.started_at = int(time.time())
            with subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=environment,
                start_new_session=os.name != "nt",
            ) as process:
                deadline = time.monotonic() + request.max_runtime_seconds
                try:
                    while process.poll() is None:
                        with Session(self.engine) as session:
                            task = session.get(ScrapeTask, request.request_id)
                            cancelled = task is None or task.cancel_requested
                        if cancelled or self.stop.wait(2):
                            status, error = (
                                "cancelled",
                                "Scrape stopped. Completed source imports are preserved.",
                            )
                            break
                        if time.monotonic() >= deadline:
                            error = "Time limit exceeded. Completed source imports are preserved."
                            break
                    else:
                        code = process.returncode
                        status = "completed" if code == 0 else "failed"
                        error = (
                            None
                            if code == 0
                            else (
                                "Another importer is running. Retry after it finishes."
                                if code == 2
                                else "Sources failed. Inspect the source outcomes below."
                            )
                        )
                finally:
                    stop_scrape_process(process, 3)
        except Exception:
            error = "The scrape process could not complete. Check backend configuration and retry."
        finally:
            try:
                with (
                    Session(self.engine) as session,
                    session.begin(),
                ):
                    now = int(time.time())
                    row = session.get(ScrapeTask, request.request_id)
                    if row is not None:
                        row.status = status
                        row.finished_at = now
                        row.error = error
                    for row in session.find(
                        ScrapeRun,
                        equal={"status": "running", "task_id": request.request_id},
                    ):
                        row.status = "failed"
                        row.finished_at = now
                        row.phase = "interrupted"
                        row.error = error or "Import ended without a final result."
            except ConflictError:
                pass
            finally:
                self.lock.release()
