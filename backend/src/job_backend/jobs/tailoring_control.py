import time
from contextlib import nullcontext
from threading import Condition, Lock, RLock

from pydantic import JsonValue, TypeAdapter

from job_backend.jobs.document_response import document_response
from job_backend.jobs.models import DocumentDetail, JobDocument, JobUserRecord
from job_backend.jobs.user_service import EditConflictError, JobNotFoundError
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.resumes.models import GenerationStage, TailoringEvent

MAX_PAUSE_SECONDS = 24 * 60 * 60
PAUSE_POLL_SECONDS = 30.0

PAUSE_EXPIRED = "Tailoring stayed paused for over a day and was stopped. Start a new attempt."
CANCELLED = "You cancelled tailoring. Reports and any finished document are kept."

_runs: dict[str, Condition] = {}
_runs_lock = Lock()


def register_run(request_id: str, write_lock: RLock) -> None:
    with _runs_lock:
        _runs[request_id] = Condition(write_lock)


def release_run(request_id: str) -> None:
    with _runs_lock:
        _runs.pop(request_id, None)


def wait_while_paused(engine: Database, request_id: str, step: str) -> None:
    with _runs_lock:
        condition = _runs.get(request_id)
    announced = False
    with condition or nullcontext():
        while True:
            with Session(engine) as session:
                row = session.get(JobDocument, request_id)
                if row is None or row.status != "running":
                    raise EditConflictError("This tailoring attempt is no longer running.")
                if row.paused_at is None:
                    return
                if pause_expired(row.paused_at):
                    with session.begin():
                        stop_expired_pause(session, row)
                    raise EditConflictError(PAUSE_EXPIRED)
                if not announced:
                    with session.begin():
                        _append_event(row, "paused", f"{step} · Paused before its next step")
                    announced = True
            if condition is None:
                time.sleep(PAUSE_POLL_SECONDS)
            else:
                condition.wait(PAUSE_POLL_SECONDS)


def pause_expired(paused_at: int | None) -> bool:
    return paused_at is not None and paused_at < int(time.time()) - MAX_PAUSE_SECONDS


def stop_expired_pause(session: Session, row: JobDocument) -> None:
    _finish(session, row, "failed", PAUSE_EXPIRED)


def pause_tailoring(engine: Database, document_id: str) -> DocumentDetail:
    with _locked(document_id), Session(engine) as session, session.begin():
        row = _running(session, document_id)
        if row.paused_at is not None:
            raise EditConflictError("This tailoring attempt is already paused.")
        row.paused_at = int(time.time())
        _append_event(row, "paused", "Pause requested · the step already running finishes first")
        session.flush()
        return document_response(session, row, DocumentDetail)


def resume_tailoring(engine: Database, document_id: str) -> DocumentDetail:
    with _runs_lock:
        live = document_id in _runs
    with _locked(document_id), Session(engine) as session, session.begin():
        row = _running(session, document_id)
        if row.paused_at is None:
            raise EditConflictError("This tailoring attempt is not paused.")
        now = int(time.time())
        if not live:
            _finish(
                session,
                row,
                "failed",
                "The backend restarted while tailoring was paused, so it cannot continue. "
                "Start a new attempt; reports and any finished document are kept.",
            )
        else:
            row.started_at = (row.started_at or row.created_at) + max(now - row.paused_at, 0)
            row.paused_at = None
            _append_event(row, "resumed", "Resumed by you")
        session.flush()
        response = document_response(session, row, DocumentDetail)
    _wake(document_id)
    return response


def cancel_tailoring(engine: Database, document_id: str) -> DocumentDetail:
    with _locked(document_id), Session(engine) as session, session.begin():
        row = _running(session, document_id)
        _finish(session, row, "cancelled", CANCELLED)
        session.flush()
        response = document_response(session, row, DocumentDetail)
    _wake(document_id)
    return response


def _running(session: Session, document_id: str) -> JobDocument:
    row = session.get(JobDocument, document_id)
    if row is None:
        raise JobNotFoundError("Document not found")
    if row.status != "running":
        raise EditConflictError("This tailoring attempt is not running.")
    return row


def _finish(session: Session, row: JobDocument, status: str, message: str) -> None:
    row.status = status
    row.finished_at = int(time.time())
    row.paused_at = None
    row.error = message
    if row.review is not None and row.review.get("status") in {"reviewing", "revising"}:
        row.review["status"] = "failed"
    for stage in row.stages:
        if stage.get("status") in {"running", "queued"}:
            stage.update(
                status=("cancelled" if status == "cancelled" else "failed")
                if stage.get("status") == "running"
                else "skipped",
                message="Cancelled by you" if status == "cancelled" else message,
            )
    _append_event(row, "cancelled" if status == "cancelled" else "error", message)
    user = session.get(JobUserRecord, row.job_id, hydrate=False)
    if user is not None and user.active_document_id == row.id:
        user.active_document_id = None


def _append_event(row: JobDocument, stage: GenerationStage, message: str) -> None:
    row.events.append(
        TypeAdapter(dict[str, JsonValue]).validate_python(
            TailoringEvent(
                id=len(row.events) + 1, created_at=int(time.time()), stage=stage, message=message
            ).model_dump(mode="json")
        )
    )


def _locked(document_id: str) -> Condition | nullcontext[None]:
    with _runs_lock:
        return _runs.get(document_id) or nullcontext()


def _wake(document_id: str) -> None:
    with _runs_lock:
        condition = _runs.get(document_id)
    if condition is not None:
        with condition:
            condition.notify_all()
