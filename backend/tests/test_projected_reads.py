from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from psycopg import Connection
from pydantic import JsonValue

from job_backend.jobs.models import Job, JobDocument, JobUserRecord
from job_backend.main import create_app
from job_backend.persistence.database import Database
from job_backend.persistence.models import Document, DocumentKey, Filter, ReadQuery
from job_backend.persistence.projections import READ_FIELDS, project_record
from job_backend.persistence.session import Session
from tests.memory_store import MemoryGateway
from tests.test_postgres import PostgresTestDatabase
from tests.test_postgres import postgres as postgres


def _jobs(count: int) -> dict[DocumentKey, Document]:
    return {
        ("jobs", f"job-{index:04}"): Job(
            id=f"job-{index:04}",
            source="test",
            source_type="user_added",
            external_id=str(index),
            company="Microsoft" if index % 2 else "Café Straße",
            title="Engineering Intern",
            locations=["Toronto, ON"],
            terms=["Summer 2027"],
            first_seen_at=index,
            date_posted=1792281600 if index % 3 else None,
            job_hash="a" * 64,
            content_hash="b" * 64,
            raw_description="Résumé Straße Café C++ SQL body marker",
            cleaned_description="Full cleaned description",
            raw_payload={"body": "x" * 100_000},
            summary="s" * 3000,
        ).to_document()
        for index in range(count)
    }


def test_pages_skip_source_documents(postgres: PostgresTestDatabase, tmp_path: Path) -> None:
    records = _jobs(120)
    postgres.gateway.commit(dict.fromkeys(records), records)
    engine = Database(postgres.gateway, tmp_path)
    with (
        patch("job_backend.main.make_engine", return_value=engine),
        TestClient(create_app(tmp_path)) as client,
    ):
        with (
            patch.object(
                postgres.gateway, "find", side_effect=AssertionError("full collection read")
            ),
            patch.object(postgres.gateway, "read", side_effect=AssertionError("full point read")),
            patch.object(
                postgres.gateway, "read_many", side_effect=AssertionError("full batch read")
            ),
            patch.object(postgres.gateway, "select", wraps=postgres.gateway.select) as select,
        ):
            response = client.get("/jobs?scope=all&sort=recent&limit=7&offset=5")
            assert response.status_code == 200, response.text
            page = response.json()
            assert page["total"] == 120
            assert [row["id"] for row in page["items"]] == [
                f"job-{i:04}" for i in range(114, 107, -1)
            ]
            assert all(
                row[field] is None
                for row in page["items"]
                for field in (
                    "raw_payload",
                    "raw_description",
                    "cleaned_description",
                    "qualifications",
                )
            )
            assert all(len(row["summary"]) == 800 for row in page["items"])
            assert len(response.content) < 20_000
            assert [call.args[0].collection for call in select.call_args_list] == [
                "jobs",
                "job_user_data",
                "job_matches",
            ]
            assert all(call.kwargs["limit"] == 7 for call in select.call_args_list)
            overview = client.get("/jobs/overview?scope=all").json()
            assert overview["total"] == 120 and overview["statuses"] == {"new": 120}
            assert client.get("/jobs?scope=all&source=&limit=1").json()["total"] == 120
            empty = client.get("/jobs?scope=all&limit=7&offset=200").json()
            assert empty["total"] == 120 and empty["items"] == []
        detail = client.get("/jobs/job-0114").json()
        assert detail["raw_payload"] == {"body": "x" * 100_000}
        assert detail["raw_description"] == "Résumé Straße Café C++ SQL body marker"
        assert detail["cleaned_description"] == "Full cleaned description"
        assert len(detail["summary"]) == 3000
        with Session(engine) as session, session.begin():
            session.add(
                JobUserRecord(job_id="job-0114", status="applied", notes="Keep these notes")
            )
        assert client.get("/jobs?scope=all&application_status=applied").json()["total"] == 1
        assert client.get("/jobs/overview").json()["statuses"] == {"new": 119, "applied": 1}
        selected = client.get("/jobs?scope=all&application_status=applied").json()["items"][0]
        assert selected["user"]["notes"] == "Keep these notes"


@pytest.mark.parametrize(
    "params",
    [
        {"q": "engineeering"},
        {"company": "Microsft"},
        {"sort": "posted"},
        {
            "posted_from": "2026-10-18",
            "posted_before": "2026-10-19",
            "posted_timezone": "America/Toronto",
        },
    ],
)
def test_postgres_matches_memory(
    postgres: PostgresTestDatabase,
    tmp_path: Path,
    params: dict[str, str],
) -> None:
    records = _jobs(9)
    records["jobs", "job-0008"]["active"] = False
    records["jobs", "job-0007"]["is_toronto_area"] = True
    records["jobs", "job-0006"]["date_posted"] = 1792281599
    records["job_user_data", "job-0005"] = JobUserRecord(
        job_id="job-0005", status="saved"
    ).to_document()
    memory = MemoryGateway()
    expected: list[JsonValue] = []
    for gateway in (memory, postgres.gateway):
        gateway.commit(dict.fromkeys(records), records)
        engine = Database(gateway, tmp_path)
        with (
            patch("job_backend.main.make_engine", return_value=engine),
            TestClient(create_app(tmp_path)) as client,
        ):
            response = client.get(
                "/jobs", params={"scope": "all", "limit": "2", "offset": "1", **params}
            )
            assert response.status_code == 200, response.text
            expected.append(response.json())
    assert expected[0] == expected[1]


def test_projection_trigger(
    postgres: PostgresTestDatabase,
) -> None:
    records = _jobs(1)
    records["job_documents", "doc"] = JobDocument(
        id="doc",
        job_id="job-0000",
        status="completed",
        created_at=1,
        job_description="Full document target",
        research={"large": "r" * 100_000},
    ).to_document()
    postgres.gateway.commit(dict.fromkeys(records), records)
    with Connection.connect(postgres.url) as connection:
        for collection, key in records:
            row = connection.execute(
                "SELECT data FROM job_record_reads WHERE collection = %s AND key = %s",
                (collection, key),
            ).fetchone()
            assert row is not None and row[0] == project_record(
                collection, records[collection, key]
            )
            assert set(row[0]) <= set(READ_FIELDS[collection])
    query = ReadQuery("jobs", fields=("id", "@revision"))
    before = postgres.gateway.select(query, limit=1).items[0]["@revision"]
    old = records["jobs", "job-0000"]
    changed: Document = {
        **old,
        "raw_description": "New searchable body",
        "new_large_field": "z" * 200_000,
    }
    postgres.gateway.commit({("jobs", "job-0000"): old}, {("jobs", "job-0000"): changed})
    after = postgres.gateway.select(query, limit=1).items[0]["@revision"]
    assert before != after
    assert (
        postgres.gateway.select(
            ReadQuery("jobs", Filter("@body", "contains", "searchable")), limit=1
        ).total
        == 1
    )
    assert postgres.gateway.read(("jobs", "job-0000")) == changed
    postgres.gateway.commit({("jobs", "job-0000"): changed}, {("jobs", "job-0000"): None})
    assert postgres.gateway.select(query, limit=1).total == 0
