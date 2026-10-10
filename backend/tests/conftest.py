from collections.abc import Generator
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from job_backend.persistence.database import Database, make_engine, migrate
from job_backend.scrape.utils.robots import RobotsCache, RobotsRules
from tests.helpers import StubNormalizer
from tests.memory_store import MemoryGateway


@pytest.fixture(autouse=True)
def isolated_logging_environment(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("JOB_LOG_LEVEL", "INFO")
    monkeypatch.setenv("JOB_LOG_DATABASE_ENABLED", "true")
    monkeypatch.setenv("JOB_DISCORD_WEBHOOK_URL", "")
    monkeypatch.setenv("JOB_DISCORD_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("JOB_DISCORD_SCRAPE_WEBHOOK_URL", "")
    monkeypatch.setenv("JOB_DISCORD_DAILY_JOBS_WEBHOOK_URL", "")
    monkeypatch.setenv("JOB_DISCORD_DAILY_JOBS_TIMEZONE", "America/New_York")
    monkeypatch.setenv("JOB_AUTH_PASSWORD_HASH", "")


@pytest.fixture(autouse=True)
def sites_without_robots_files(monkeypatch: MonkeyPatch) -> None:
    # tests stay offline, so every site acts as if it had no robots.txt
    monkeypatch.setattr(
        "job_backend.scrape.utils.robots._cache", RobotsCache(lambda _url: RobotsRules())
    )


@pytest.fixture(autouse=True)
def immediate_connect_retries(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("job_backend.common.ai_completion.CONNECT_RETRY_SECONDS", 0.0)


@pytest.fixture
def engine(tmp_path: Path) -> Generator[Database]:
    database = make_engine(tmp_path / "postgres")
    migrate(database)
    try:
        yield database
    finally:
        database.dispose()


@pytest.fixture
def normalizer() -> StubNormalizer:
    return StubNormalizer()


@pytest.fixture(autouse=True)
def isolated_postgres(monkeypatch: MonkeyPatch) -> None:
    stores: dict[Path, MemoryGateway] = {}

    def gateway(path: Path, connection_url: str | None = None) -> MemoryGateway:
        key = path.resolve()
        if key not in stores:
            stores[key] = MemoryGateway()
        return stores[key]

    monkeypatch.setattr("job_backend.persistence.database._open_gateway", gateway)
