from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from job_backend.jobs.models import Job, JobCreate, JobPage, JobResponse
from job_backend.jobs.storage import save_user_job
from job_backend.main import create_app
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.scrape.pipeline.models import FetchResult
from job_backend.scrape.pipeline.pipeline import scrape_source
from tests.helpers import ADAPTER, StubNormalizer, listing, payload


def test_description_only_job(tmp_path: Path) -> None:
    path = tmp_path / "postgres"
    description = "Build tools.\n\nRequirements: Python and SQL."
    with TestClient(create_app(path)) as client:
        response = client.post("/jobs", json={"raw_description": description})
        assert response.status_code == 200
        saved = JobResponse.model_validate_json(response.content)
        assert saved.source_type == "user_added"
        assert saved.application_url is None and saved.qualifications is None
        assert saved.is_canada_internship is None and saved.is_toronto_area is None
        assert saved.raw_description == description
        assert saved.company == saved.title == "Not specified"
        again = client.post("/jobs", json={"raw_description": description})
        assert JobResponse.model_validate_json(again.content).id == saved.id
    with TestClient(create_app(path)) as client:
        page = JobPage.model_validate_json(client.get("/jobs").content)
        assert [item.id for item in page.items] == [saved.id]
        assert page.items[0].raw_description is None
        assert JobResponse.model_validate_json(client.get(f"/jobs/{saved.id}").content) == saved
        day = client.get(
            "/jobs",
            params={
                "first_seen_from": saved.first_seen_at,
                "first_seen_before": saved.first_seen_at + 1,
            },
        )
        assert JobPage.model_validate_json(day.content).total == 1
        assert JobPage.model_validate_json(client.get("/jobs?toronto_area=true").content).total == 0


@pytest.mark.parametrize(
    "invalid",
    [
        {"raw_description": "   \n"},
        {"raw_description": "a" * 5_000_001},
        {"raw_description": "Job", "application_url": "javascript:alert(1)"},
    ],
)
def test_invalid_user_jobs_are_not_saved(tmp_path: Path, invalid: dict[str, str]) -> None:
    with TestClient(create_app(tmp_path / "postgres")) as client:
        assert client.post("/jobs", json=invalid).status_code == 422
        assert JobPage.model_validate_json(client.get("/jobs").content).total == 0


@pytest.mark.parametrize("manual_first", [False, True])
def test_save_reuses_url(
    engine: Database,
    normalizer: StubNormalizer,
    manual_first: bool,
) -> None:
    entry = JobCreate(
        raw_description="Pasted details",
        application_url="https://example.com/jobs/example-1?utm_source=email",
    )
    if manual_first:
        with Session(engine) as session:
            save_user_job(session, entry, "user_added")
    run = scrape_source(
        engine, ADAPTER, lambda _etag: FetchResult(payload(listing()), None), normalizer=normalizer
    )
    assert run.created == 1
    with Session(engine) as session:
        saved = save_user_job(session, entry, "user_auto_add")
        assert saved.source_type == ("user_added" if manual_first else "scraped")
        assert saved.company == ("Not specified" if manual_first else "Example Company")
        assert saved.is_canada_internship is (None if manual_first else True)
        assert len(session.find(Job)) == (2 if manual_first else 1)
