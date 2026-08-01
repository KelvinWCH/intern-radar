import logging
from pathlib import Path
from threading import Event

import pytest

from job_backend.matching.worker import FAILURE_BACKOFF, MatchMaintenance
from job_backend.persistence.database import Database
from tests.matching.helpers import FakeEmbedder, add_job, profile, save


def test_failure_backoff(engine: Database, caplog: pytest.LogCaptureFixture) -> None:
    save(engine, profile())
    add_job(engine, "job-swe", "Software Engineering Intern")
    now = [0.0]

    def broken() -> FakeEmbedder:
        raise OSError("model download failed")

    maintenance = MatchMaintenance(
        Path("unused"),
        Event(),
        engine_factory=lambda _path: engine,
        embedder_factory=broken,
        interval=60.0,
        clock=lambda: now[0],
    )
    with caplog.at_level(logging.WARNING):
        maintenance(after_batch=True)
        maintenance(after_batch=True)
        now[0] = 60.0 * FAILURE_BACKOFF - 1
        maintenance(after_batch=False)
    warnings = [record for record in caplog.records if "matching pass failed" in record.message]
    assert len(warnings) == 1
