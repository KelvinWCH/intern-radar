import json
import logging
from collections.abc import Generator
from pathlib import Path

import pytest
from pydantic import JsonValue
from pytest import CaptureFixture

from job_backend.common.logger import configure_logging, get_logger, shutdown_logging
from job_backend.common.models import LogEntry, LoggingSettings
from job_backend.persistence.database import Database, make_engine
from job_backend.persistence.session import Session

WEBHOOK = "https://discord.com/api/webhooks/123/fictional-token"


@pytest.fixture
def engine(tmp_path: Path) -> Generator[Database]:
    database = make_engine(tmp_path / "logging-state")
    try:
        yield database
    finally:
        shutdown_logging()
        database.dispose()


@pytest.fixture(autouse=True)
def close_logging() -> Generator[None]:
    yield
    shutdown_logging()


def test_log_handlers(engine: Database, capsys: CaptureFixture[str]) -> None:
    configure_logging(engine=engine, settings=LoggingSettings(database_enabled=True))
    logger = get_logger(__name__)
    context: dict[str, JsonValue] = {"source": "example", "run_id": 42}
    logger.info("Imported %s jobs", 3, extra={"context": context})
    context["run_id"] = 99
    logger.debug("Filtered debug message")
    try:
        raise ValueError("fictional failure")
    except ValueError:
        logger.exception("Import failed")
    shutdown_logging()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("Imported 3 jobs") == 1
    assert "ValueError: fictional failure" in captured.err
    assert "Filtered debug message" not in captured.err
    with Session(engine) as session:
        entries = list(session.find(LogEntry, order_by=("created_at", "id")))
        assert len(entries) == 2
        assert entries[0].context == {"source": "example", "run_id": 42}
        assert entries[0].created_at > 0 and entries[0].line_number > 0
        assert entries[0].logger == "job_backend." + __name__
        assert entries[0].message == "Imported 3 jobs" and entries[0].exception is None
        assert entries[1].message == "Import failed"
        assert entries[1].level == "ERROR"
        assert entries[1].exception is not None
        assert "ValueError: fictional failure" in entries[1].exception


def test_discord_redacts_tokens() -> None:
    from job_backend.common.discord import log_payload

    record = logging.LogRecord("job_backend.tests", logging.ERROR, __file__, 1, WEBHOOK, (), None)
    record.exc_text = "Traceback\n" + "frame\n" * 1500 + "ConnectError: [WinError 10013] " + WEBHOOK
    payload = log_payload(record)
    encoded = json.dumps(payload)
    assert "WinError 10013" in encoded
    assert "fictional-token" not in encoded
    assert "[Discord webhook redacted]" in encoded
    assert "Windows blocked a network connection" in encoded
    assert "Traceback" not in encoded and "frame" not in encoded
    assert "```text" in encoded
