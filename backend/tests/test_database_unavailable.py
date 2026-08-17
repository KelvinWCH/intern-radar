import time
from threading import Event
from unittest.mock import patch

import httpx2
import pytest
from fastapi.testclient import TestClient
from psycopg import OperationalError
from pydantic import SecretStr
from pytest import CaptureFixture, MonkeyPatch

from job_backend.common.logger import configure_logging
from job_backend.common.models import LoggingSettings
from job_backend.main import create_app
from job_backend.persistence.database import Database
from job_backend.persistence.errors import DatabaseUnavailableError


@pytest.fixture
def discord_requests(monkeypatch: MonkeyPatch) -> list[httpx2.Request]:
    requests: list[httpx2.Request] = []

    def deliver(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(204)

    def configure(*, engine: Database | None = None) -> None:
        configure_logging(
            engine=engine,
            settings=LoggingSettings(
                database_enabled=True,
                discord_webhook_url=SecretStr("https://discord.com/api/webhooks/123/test-token"),
            ),
            discord_transport=httpx2.MockTransport(deliver),
        )

    monkeypatch.setattr("job_backend.main.configure_logging", configure)
    return requests


def test_outage_is_retryable(engine: Database, discord_requests: list[httpx2.Request]) -> None:
    with (
        patch("job_backend.main.make_engine", return_value=engine),
        TestClient(create_app(engine.local_path)) as client,
        patch.object(engine.gateway, "select", side_effect=DatabaseUnavailableError()),
    ):
        response = client.get("/jobs")
        assert response.status_code == 503
        assert response.json() == {
            "detail": "The database is temporarily unavailable. Please try again.",
            "code": "database_unavailable",
        }
        assert response.headers["Retry-After"] == "5"
        assert client.get("/health").status_code == 200
        assert client.get("/jobs").status_code == 503
    assert len(discord_requests) == 1
    assert b"PostgreSQL is unavailable" in discord_requests[0].content


@pytest.mark.parametrize("stage", ["migration", "scrape_recovery"])
def test_startup_outage_recovers(
    engine: Database,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    discord_requests: list[httpx2.Request],
    stage: str,
) -> None:
    monkeypatch.setattr("job_backend.main._DATABASE_RETRY_SECONDS", 0.01)
    retry_started = Event()
    release_retry = Event()
    attempts = 0

    def initialize(*_args: object) -> None:
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            raise DatabaseUnavailableError() from OperationalError(
                "postgresql://private:secret@unavailable/database"
            )
        retry_started.set()
        assert release_retry.wait(timeout=5)

    target = (
        "job_backend.main.migrate"
        if stage == "migration"
        else "job_backend.main.ScrapeController.recover"
    )
    with (
        patch("job_backend.main.make_engine", return_value=engine),
        patch(target, side_effect=initialize),
        TestClient(create_app(engine.local_path)) as client,
    ):
        try:
            assert retry_started.wait(timeout=5)
            assert client.get("/health").json() == {"status": "ok"}
            assert client.get("/openapi.json").status_code == 200
            with patch.object(engine.gateway, "find") as find:
                for method, path in [("GET", "/jobs"), ("POST", "/jobs"), ("GET", "/scrapes")]:
                    response = client.request(method, path)
                    assert response.status_code == 503
                    assert response.json()["code"] == "database_unavailable"
                    assert response.headers["Retry-After"] == "5"
                find.assert_not_called()
        finally:
            release_retry.set()
        deadline = time.monotonic() + 5
        while client.get("/jobs").status_code == 503:
            assert time.monotonic() < deadline, "API did not recover after PostgreSQL returned"
            time.sleep(0.01)
        assert client.get("/jobs").status_code == 200
        assert attempts == 3
    assert len(discord_requests) == 1
    alert = discord_requests[0].content.decode()
    output = capsys.readouterr().err
    assert "during API startup" in alert
    assert "PostgreSQL connection restored" in output
    assert "secret" not in alert + output
    assert "private" not in alert + output
    assert "Traceback" not in alert + output
