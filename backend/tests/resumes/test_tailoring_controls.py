import time
from collections.abc import Callable
from pathlib import Path
from threading import Thread
from uuid import uuid4

import httpx2
import pytest
from fastapi.testclient import TestClient

from job_backend.jobs.models import (
    JobDocument,
    JobResponse,
    JobUserRecord,
    PreparedTailoring,
    TailorRequest,
)
from job_backend.jobs.tailoring import (
    get_document,
    prepare_tailoring,
    run_tailoring_background,
)
from job_backend.jobs.tailoring_control import (
    CANCELLED,
    MAX_PAUSE_SECONDS,
    PAUSE_EXPIRED,
    cancel_tailoring,
    pause_tailoring,
    resume_tailoring,
)
from job_backend.jobs.user_service import EditConflictError
from job_backend.main import create_app
from job_backend.persistence.database import Database, make_engine
from job_backend.persistence.session import Session
from job_backend.resumes.dependencies import resume_ai_settings
from tests.resumes.helpers import (
    completion,
    resume,
    selection,
    settings,
    workflow_response,
)


def saved_job(path: Path) -> tuple[Database, str]:
    app = create_app(path)
    app.dependency_overrides[resume_ai_settings] = settings
    with TestClient(app) as client:
        client.put("/resumes/profile", json=resume().model_dump())
        job = JobResponse.model_validate_json(
            client.post("/jobs", json={"raw_description": "Build Python APIs"}).content
        )
    return make_engine(path), job.id


def reserve(engine: Database, job_id: str, request_id: str) -> PreparedTailoring:
    prepared = prepare_tailoring(
        engine, job_id, TailorRequest(request_id=request_id, include_cover_letter=False), settings()
    )
    assert isinstance(prepared, PreparedTailoring)
    return prepared


def wait_for(check: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 10
    while not check():
        assert time.monotonic() < deadline, "Timed out waiting for the worker"
        time.sleep(0.02)


def paused_before_next_step(engine: Database, request_id: str) -> bool:
    events = get_document(engine, request_id).events
    return any(event.message == "Resume: paused before its next step" for event in events)


def test_pause_and_resume(tmp_path: Path) -> None:
    engine, job_id = saved_job(tmp_path / "postgres")
    request_id = str(uuid4())
    writer_calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal writer_calls
        response = workflow_response(request)
        if response is not None:
            return response
        writer_calls += 1
        if writer_calls == 1:
            assert pause_tailoring(engine, request_id).paused_at is not None
        return completion(selection().model_dump_json())

    prepared = reserve(engine, job_id, request_id)
    worker = Thread(
        target=run_tailoring_background,
        args=(engine, prepared, httpx2.MockTransport(handler)),
    )
    worker.start()
    try:
        wait_for(lambda: paused_before_next_step(engine, request_id))
        time.sleep(0.1)
        held = get_document(engine, request_id)
        assert held.status == "running" and held.paused_at is not None
        assert held.resume is None and writer_calls == 1
        with pytest.raises(EditConflictError, match="already paused"):
            pause_tailoring(engine, request_id)
        with pytest.raises(EditConflictError, match="already running"):
            reserve(engine, job_id, str(uuid4()))
        resumed = resume_tailoring(engine, request_id)
        assert resumed.status == "running" and resumed.paused_at is None
    finally:
        worker.join(10)
    assert not worker.is_alive()
    done = get_document(engine, request_id)
    assert done.status == "completed" and done.resume is not None, done.events[-1].details
    assert done.paused_at is None
    stages = [event.stage for event in done.events]
    assert stages.index("paused") < stages.index("resumed") < stages.index("done")
    with pytest.raises(EditConflictError, match="not running"):
        cancel_tailoring(engine, request_id)
    engine.dispose()


def test_cancel_paused(tmp_path: Path) -> None:
    engine, job_id = saved_job(tmp_path / "postgres")
    request_id = str(uuid4())
    writer_calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal writer_calls
        response = workflow_response(request)
        if response is not None:
            return response
        writer_calls += 1
        pause_tailoring(engine, request_id)
        return completion(selection().model_dump_json())

    worker = Thread(
        target=run_tailoring_background,
        args=(engine, reserve(engine, job_id, request_id), httpx2.MockTransport(handler)),
    )
    worker.start()
    try:
        wait_for(lambda: paused_before_next_step(engine, request_id))
        cancelled = cancel_tailoring(engine, request_id)
    finally:
        worker.join(5)
    assert not worker.is_alive()
    assert cancelled.status == "cancelled" and cancelled.error == CANCELLED
    assert cancelled.paused_at is None and cancelled.finished_at is not None
    saved = get_document(engine, request_id)
    assert saved.status == "cancelled" and saved.resume is None and writer_calls == 1
    assert {stage.key: stage.status for stage in saved.stages} == {
        "research": "completed",
        "resume": "cancelled",
        "cover_letter": "skipped",
        "pdf_diagnostics": "skipped",
        "reviewer": "skipped",
    }
    assert saved.events[-1].stage == "cancelled" and saved.events[-1].message == CANCELLED
    assert saved.ai_usage is not None and saved.ai_usage.calls >= 3
    with pytest.raises(EditConflictError):
        resume_tailoring(engine, request_id)
    assert reserve(engine, job_id, str(uuid4())).document.status == "running"
    engine.dispose()


def paused_row(engine: Database, *, paused_for: int, started_ago: int) -> str:
    document_id = str(uuid4())
    now = int(time.time())
    with Session(engine) as session:
        session.add(
            JobDocument(
                id=document_id,
                job_id="paused-job",
                company="Example",
                title="Intern",
                status="running",
                created_at=now - started_ago,
                started_at=now - started_ago,
                paused_at=now - paused_for,
                stages=[
                    {
                        "key": "resume",
                        "label": "Resume",
                        "model": "test-writer",
                        "status": "running",
                        "message": "Sending to AI",
                    }
                ],
            )
        )
        session.add(JobUserRecord(job_id="paused-job", active_document_id=document_id))
        session.commit()
    return document_id


def test_old_pause_stopped(engine: Database) -> None:
    document_id = paused_row(engine, paused_for=MAX_PAUSE_SECONDS + 60, started_ago=90000)
    expired = get_document(engine, document_id)
    assert expired.status == "failed" and expired.error == PAUSE_EXPIRED
    assert expired.paused_at is None
    with Session(engine) as session:
        user = session.find(JobUserRecord, equal={"job_id": "paused-job"}).one()
        assert user.active_document_id is None
