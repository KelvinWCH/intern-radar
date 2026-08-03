from pathlib import Path

from fastapi.testclient import TestClient

from job_backend.jobs.models import Job
from job_backend.main import create_app
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.scrape.pipeline.models import FetchResult
from job_backend.scrape.pipeline.pipeline import scrape_source
from tests.helpers import ADAPTER, StubNormalizer, listing, payload


def test_delete_restore_and_rescrape(engine: Database, normalizer: StubNormalizer) -> None:
    row = listing()
    scrape_source(
        engine, ADAPTER, lambda _etag: FetchResult(payload(row), None), normalizer=normalizer
    )
    with Session(engine) as session:
        identifier = session.all(Job)[0].id
    assert engine.local_path is not None
    with TestClient(create_app(Path(engine.local_path))) as client:
        update = client.put(
            f"/jobs/{identifier}/user",
            json={
                "status": "saved",
                "notes": "Keep these notes",
                "version": 0,
            },
        )
        assert update.status_code == 200
        deleted = client.delete(f"/jobs/{identifier}")
        assert deleted.status_code == 200 and deleted.json()["deleted_at"] is not None
        assert (
            client.delete(f"/jobs/{identifier}").json()["deleted_at"]
            == deleted.json()["deleted_at"]
        )
        assert client.get("/jobs").json()["total"] == 0
        assert client.get("/jobs", params={"scope": "all"}).json()["total"] == 0
        assert client.get("/jobs/overview").json()["total"] == 0
        trash = client.get("/jobs", params={"scope": "all", "deleted": True}).json()
        assert trash["total"] == 1 and trash["items"][0]["user"]["notes"] == "Keep these notes"
        row["title"] = "Updated Software Intern"
        scrape_source(
            engine, ADAPTER, lambda _etag: FetchResult(payload(row), None), normalizer=normalizer
        )
        assert client.get("/jobs").json()["total"] == 0
        restored = client.post(f"/jobs/{identifier}/restore")
        assert restored.status_code == 200 and restored.json()["deleted_at"] is None
        assert restored.json()["title"] == row["title"]
        assert restored.json()["user"]["notes"] == "Keep these notes"
        assert restored.json()["user"]["status"] == "saved"
        assert client.get("/jobs/overview").json()["total"] == 1
        assert client.get("/jobs", params={"deleted": True}).json()["total"] == 0
        assert client.delete("/jobs/999999").status_code == 404
        assert client.post("/jobs/999999/restore").status_code == 404
