import time
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from job_backend.main import create_app
from job_backend.persistence.database import make_engine, migrate
from job_backend.resumes.dependencies import resume_ai_settings
from job_backend.scrape.control import service
from job_backend.scrape.control.catalog import build_scrape_command, list_sources
from job_backend.scrape.control.models import ScrapeRequest, ScrapeTaskResponse
from job_backend.scrape.control.service import ScrapeController
from tests.resumes.helpers import settings


def _request() -> ScrapeRequest:
    return ScrapeRequest(
        request_id=str(uuid4()),
        sources=[next(source.id for source in list_sources() if source.enabled)],
        max_ai_calls=3,
        max_downloads=5,
        max_age_days=4,
    )


def test_rejects_unknown_sources(tmp_path: Path) -> None:
    request = _request()
    for source in [
        "https://unknown.example",
        "github:--all",
        *[item.id for item in list_sources() if not item.enabled][:1],
    ]:
        request.sources = [source]
        with pytest.raises(ValueError, match="available sources"):
            build_scrape_command(request, tmp_path / "database")
    request.sources = [next(item.id for item in list_sources() if item.group == "company")]
    command = build_scrape_command(request, tmp_path / "database")
    assert command[command.index("--trigger") + 1] == "manual"
    assert "--all-companies" not in command
    assert "--unattended" not in command


@pytest.mark.parametrize("include_older_postings", [False, True])
def test_supervisor_completion(
    tmp_path: Path, monkeypatch: MonkeyPatch, include_older_postings: bool
) -> None:
    engine = make_engine(tmp_path / "database")
    engine.connection_url = "postgresql://selected-database/jobs"
    migrate(engine)
    process = MagicMock()
    process.__enter__.return_value = process
    process.poll.return_value = 0
    process.returncode = 0
    launch = MagicMock(return_value=process)
    monkeypatch.setattr(service.subprocess, "Popen", launch)
    monkeypatch.setattr(service, "stop_scrape_process", MagicMock())
    controller = ScrapeController(engine)
    try:
        request = _request()
        request.include_older_postings = include_older_postings
        queued = controller.start(request)
        assert queued.status == "queued"
        assert controller.thread is not None
        controller.thread.join(timeout=5)
        assert not controller.thread.is_alive()
        finished = controller.start(request)
        assert finished.status == "completed" and finished.finished_at is not None
        assert finished.started_at is not None and finished.elapsed_seconds >= 0
        launch.assert_called_once()
        environment = launch.call_args.kwargs["env"]
        assert environment["JOB_DATABASE_URL"] == "postgresql://selected-database/jobs"
        assert environment["JOB_AI_MAX_CALLS_PER_IMPORT"] == "3"
        assert environment["JOB_PAGE_MAX_DOWNLOADS"] == "5"
        assert environment["JOB_GITHUB_MAX_AGE_DAYS"] == ("0" if include_older_postings else "4")
        assert not controller.lock.is_locked
    finally:
        controller.close()
        engine.dispose()


def test_cancel_running_task(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    database = tmp_path / "database"
    engine = make_engine(database)
    started = Event()
    process = MagicMock()
    process.__enter__.return_value = process

    def poll() -> None:
        started.set()

    process.poll.side_effect = poll
    launch = MagicMock(return_value=process)
    stop = MagicMock()
    monkeypatch.setattr(service.subprocess, "Popen", launch)
    monkeypatch.setattr(service, "stop_scrape_process", stop)
    app = create_app(database)
    app.dependency_overrides[resume_ai_settings] = settings
    try:
        with TestClient(app) as client:
            request = _request()
            response = client.post("/scrapes", json=request.model_dump())
            assert response.status_code == 202
            assert started.wait(5)
            replay = client.post("/scrapes", json=request.model_dump())
            assert replay.status_code == 202
            assert client.post("/scrapes", json=_request().model_dump()).status_code == 409
            cancellation = client.post(f"/scrapes/{request.request_id}/cancel")
            assert ScrapeTaskResponse.model_validate_json(
                cancellation.content, extra="ignore"
            ).cancel_requested
            task = ScrapeTaskResponse.model_validate_json(cancellation.content, extra="ignore")
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                task = ScrapeTaskResponse.model_validate_json(
                    client.get(f"/scrapes/{request.request_id}").content, extra="ignore"
                )
                if task.status == "cancelled":
                    break
                Event().wait(0.05)
            assert task.status == "cancelled" and task.finished_at is not None
            assert client.get("/scrapes/missing").status_code == 404
            assert (
                client.post(
                    "/scrapes", json={**request.model_dump(), "max_ai_calls": 101}
                ).status_code
                == 422
            )
            launch.assert_called_once()
            stop.assert_called_once_with(process, 3)
    finally:
        engine.dispose()
