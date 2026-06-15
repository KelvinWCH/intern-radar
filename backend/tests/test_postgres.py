import os
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg import Connection, sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import tuple_row
from pytest import MonkeyPatch

from job_backend.jobs.identity import job_document_id
from job_backend.jobs.models import Job, JobPage, JobResponse
from job_backend.main import create_app
from job_backend.persistence.database import Database, migrate
from job_backend.persistence.errors import ConflictError
from job_backend.persistence.models import Document, DocumentKey
from job_backend.persistence.postgres import PostgresGateway
from job_backend.persistence.session import Session
from job_backend.scrape.pipeline.models import FetchResult
from job_backend.scrape.pipeline.pipeline import scrape_source
from tests.helpers import ADAPTER, StubNormalizer, listing, payload


@dataclass
class PostgresTestDatabase:
    url: str
    gateway: PostgresGateway


@pytest.fixture
def postgres() -> Generator[PostgresTestDatabase]:
    server_url = os.environ.get("JOB_TEST_DATABASE_URL", "")
    if not server_url:
        pytest.skip("Set JOB_TEST_DATABASE_URL to run real PostgreSQL integration tests")
    schema = "test_job_" + uuid4().hex
    connection: Connection[tuple[object, ...]] = Connection.connect(
        server_url, autocommit=True, row_factory=tuple_row
    )
    with connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    url = make_conninfo(server_url, options=f"-c search_path={schema}")
    gateway = PostgresGateway(url)
    try:
        yield PostgresTestDatabase(url, gateway)
    finally:
        gateway.close()
        with Connection.connect(server_url, autocommit=True, row_factory=tuple_row) as cleanup:
            cleanup.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def _insert(gateway: PostgresGateway, records: dict[DocumentKey, Document]) -> None:
    gateway.commit(dict.fromkeys(records), records)


def test_postgres_large_documents(
    postgres: PostgresTestDatabase,
) -> None:
    data: Document = {
        "title": "Ingénieur 日本語",
        "raw_payload": {"nested": [[1, 2], ["日本語", None]], "items": []},
        "description": "Complete job content\n" * 100_000,
    }
    _insert(postgres.gateway, {("jobs", "large"): data, ("notes", "large"): {"value": 2}})
    assert postgres.gateway.read_many(
        [("jobs", "large"), ("jobs", "missing"), ("notes", "large"), ("jobs", "large")]
    ) == {("jobs", "large"): data, ("jobs", "missing"): None, ("notes", "large"): {"value": 2}}


def test_postgres_rollback(postgres: PostgresTestDatabase) -> None:
    gateway = postgres.gateway
    _insert(gateway, {("jobs", "guard"): {"value": 1}, ("jobs", "delete"): {"value": 1}})
    expected = gateway.read_many([("jobs", "guard"), ("jobs", "delete"), ("jobs", "new")])
    gateway.commit({("jobs", "guard"): {"value": 1}}, {("jobs", "guard"): {"value": 2}})
    with pytest.raises(ConflictError):
        gateway.commit(expected, {("jobs", "delete"): None, ("jobs", "new"): {"value": 3}})
    assert gateway.read(("jobs", "delete")) == {"value": 1}
    assert gateway.read(("jobs", "new")) is None


def test_postgres_concurrent_create(postgres: PostgresTestDatabase) -> None:
    postgres.gateway.initialize()
    barrier = Barrier(2)

    def insert(value: int) -> bool:
        barrier.wait(timeout=5)
        try:
            postgres.gateway.commit({("jobs", "one"): None}, {("jobs", "one"): {"value": value}})
            return True
        except ConflictError:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(insert, [1, 2])) == [False, True]
    assert len(postgres.gateway.find("jobs", {})) == 1


def test_postgres_checksum(postgres: PostgresTestDatabase) -> None:
    postgres.gateway.initialize()
    connection: Connection[tuple[object, ...]] = Connection.connect(
        postgres.url, row_factory=tuple_row
    )
    with connection:
        connection.execute("UPDATE job_schema_migrations SET checksum = 'different'")
    other = PostgresGateway(postgres.url)
    try:
        with pytest.raises(RuntimeError, match="migration changed"):
            other.initialize()
    finally:
        other.close()


def test_postgres_api(
    postgres: PostgresTestDatabase, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("JOB_LOG_DATABASE_ENABLED", "false")
    database = Database(postgres.gateway, tmp_path / "postgres")

    def engine(_path: Path | None = None) -> Database:
        return database

    monkeypatch.setattr("job_backend.main.make_engine", engine)
    with TestClient(create_app(database.local_path)) as client:
        assert JobPage.model_validate_json(client.get("/jobs").content).total == 0
        created = client.post(
            "/jobs",
            json={
                "raw_description": "Build Python tools and query SQL databases.",
                "application_url": "https://example.com/jobs/postgres",
            },
        )
        assert created.status_code == 200
        job = JobResponse.model_validate_json(created.content)
        assert JobResponse.model_validate_json(client.get(f"/jobs/{job.id}").content).id == job.id
        assert JobPage.model_validate_json(client.get("/jobs").content).total == 1
        update = client.put(
            f"/jobs/{job.id}/user",
            json={"status": "saved", "notes": "Durable PostgreSQL notes", "version": 0},
        )
        assert update.status_code == 200
        assert client.delete(f"/jobs/{job.id}").status_code == 200
        assert JobPage.model_validate_json(client.get("/jobs").content).total == 0
        restored = client.post(f"/jobs/{job.id}/restore")
        assert restored.status_code == 200
        record = JobResponse.model_validate_json(restored.content)
        assert record.user is not None and record.user.notes == "Durable PostgreSQL notes"
    with TestClient(create_app(database.local_path)) as restarted:
        reloaded = JobResponse.model_validate_json(restarted.get(f"/jobs/{job.id}").content)
        assert reloaded.user is not None and reloaded.user.notes == "Durable PostgreSQL notes"
        assert reloaded.deleted_at is None


def test_postgres_liveness(
    postgres: PostgresTestDatabase, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr("job_backend.scrape.pipeline.liveness.CONFIRM_AFTER_SECONDS", 0)
    database = Database(postgres.gateway, tmp_path / "postgres")
    migrate(database)
    board = replace(ADAPTER, complete_listing=True)

    def run(*ids: str) -> None:
        data = payload(*(listing(identity) for identity in ids))
        scrape_source(
            database, board, lambda _etag: FetchResult(data, None), normalizer=StubNormalizer()
        )

    def active(identity: str) -> bool | None:
        with Session(database) as session:
            job = session.get(Job, job_document_id(board.name, identity), hydrate=False)
            assert job is not None
            return job.active

    run("a", "b")
    run("a")
    assert active("b") is True
    run("a")
    assert active("b") is False
    run("a", "b")
    assert active("b") is not False
