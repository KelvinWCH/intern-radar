from pathlib import Path

from fastapi.testclient import TestClient

from job_backend.jobs.models import Job, JobPage, JobResponse
from job_backend.main import create_app
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.scrape.pipeline.models import FetchResult
from job_backend.scrape.pipeline.pipeline import scrape_source
from tests.helpers import ADAPTER, StubNormalizer, listing, payload


def test_browse_jobs_and_import_history(engine: Database, normalizer: StubNormalizer) -> None:
    assert engine.local_path is not None
    data = payload(listing(), listing("closed", active=False), listing("hidden", visible=False))
    scrape_source(engine, ADAPTER, lambda _etag: FetchResult(data, None), normalizer=normalizer)
    with TestClient(create_app(Path(engine.local_path))) as client:
        response = client.get("/jobs", params={"limit": 1})
        assert response.status_code == 200
        page = JobPage.model_validate_json(response.content)
        assert page.total == 1 and page.limit == 1
        assert page.items[0].summary is None
        assert len(page.items[0].job_hash) == len(page.items[0].content_hash) == 64
        assert page.items[0].source_url is not None
        assert response.json()["items"][0]["raw_payload"] is None
        saved = JobResponse.model_validate_json(client.get(f"/jobs/{page.items[0].id}").content)
        assert saved.raw_payload is not None
        assert saved.raw_payload["id"] == page.items[0].external_id
        assert page.items[0].last_changed_at == page.items[0].first_seen_at
        assert page.items[0].terms == ["Summer 2027"]
        closed = JobPage.model_validate_json(client.get("/jobs?active=false").content)
        assert closed.total == 1
        detail = client.get(f"/jobs/{closed.items[0].id}")
        assert JobResponse.model_validate_json(detail.content).active is False
        assert JobPage.model_validate_json(client.get("/jobs?offset=1").content).items == []
        assert client.get("/jobs?limit=101").status_code == 422
        assert client.get("/jobs?offset=-1").status_code == 422
        assert client.get("/jobs/999999").status_code == 404
        assert client.get("/openapi.json").status_code == 200


def test_all_jobs_scope(engine: Database) -> None:
    with Session(engine) as session, session.begin():
        for index, identity in enumerate(("eligible", "closed", "hidden", "unknown", "deleted")):
            session.add(
                Job(
                    id=identity,
                    source=identity,
                    title=identity,
                    is_canada_internship=None if identity == "unknown" else True,
                    is_toronto_area=None if identity == "unknown" else False,
                    active=identity != "closed",
                    is_visible=identity != "hidden",
                    deleted_at=1 if identity == "deleted" else None,
                    first_seen_at=index,
                    job_hash="a" * 64,
                    content_hash="b" * 64,
                )
            )
    assert engine.local_path is not None
    with TestClient(create_app(Path(engine.local_path))) as client:
        query = {"scope": "all", "activity": "all", "limit": 2, "sort": "recent"}
        first = JobPage.model_validate_json(client.get("/jobs", params=query).content)
        second = JobPage.model_validate_json(
            client.get("/jobs", params={**query, "offset": 2}).content
        )
        assert first.total == second.total == 4
        assert [job.id for job in [*first.items, *second.items]] == [
            "unknown",
            "hidden",
            "closed",
            "eligible",
        ]
        eligible = client.get("/jobs?scope=eligible&activity=all").json()
        assert eligible["total"] == 2
        for scope, sources in (
            ("eligible", ["closed", "eligible"]),
            ("all", ["closed", "eligible", "hidden", "unknown"]),
        ):
            counts = client.get("/jobs/overview", params={"scope": scope}).json()
            assert counts["total"] == counts["statuses"]["new"] == len(sources)
            assert counts["sources"] == sources
        deleted = client.get("/jobs", params={**query, "deleted": True}).json()
        assert deleted["total"] == 1 and deleted["items"][0]["id"] == "deleted"
        assert client.get("/jobs/overview?scope=all&deleted=true").json()["total"] == 1
