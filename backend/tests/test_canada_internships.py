from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from job_backend.jobs.models import Job, JobPage
from job_backend.main import create_app
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.scrape.pipeline.models import (
    ExtractedJob,
    ExtractionResult,
    FetchResult,
)
from job_backend.scrape.pipeline.pipeline import scrape_source
from tests.helpers import ADAPTER, StubNormalizer, listing, normalized_listing, payload


def test_unrelated_postings_excluded(
    engine: Database,
) -> None:
    toronto = listing("toronto")
    elsewhere = listing("elsewhere")
    elsewhere.update(locations=["Vancouver, BC, Canada"], test_ai_toronto_area=False)
    unclear = listing("unclear")
    unclear.update(
        locations=["Remote"], test_ai_canada_internship=False, test_ai_toronto_area=False
    )
    us_role = listing("us-role")
    us_role.update(
        locations=["Seattle, WA"], test_ai_canada_internship=False, test_ai_toronto_area=False
    )
    full_time = listing("full-time", title="Software Engineer New Grad")
    full_time["test_ai_canada_internship"] = False
    data = payload(toronto, elsewhere, unclear, us_role, full_time)
    normalizer = StubNormalizer()
    run = scrape_source(
        engine, ADAPTER, lambda _etag: FetchResult(data, None), normalizer=normalizer
    )
    assert run.created == 3 and run.matched == 2
    assert normalizer.calls == 3
    with Session(engine) as session:
        assert {row.external_id for row in session.find(Job)} == {"toronto", "elsewhere", "unclear"}
    assert engine.local_path is not None
    with TestClient(create_app(Path(engine.local_path))) as client:
        all_jobs = JobPage.model_validate_json(client.get("/jobs").content)
        assert all_jobs.total == 2
        assert all(job.is_canada_internship is True for job in all_jobs.items)
        nearby = JobPage.model_validate_json(client.get("/jobs?toronto_area=true").content)
        other = JobPage.model_validate_json(client.get("/jobs?toronto_area=false").content)
        assert nearby.total == other.total == 1
        assert nearby.items[0].external_id == "toronto" and nearby.items[0].is_toronto_area is True
        assert other.items[0].external_id == "elsewhere" and other.items[0].is_toronto_area is False
        assert client.get("/jobs?toronto_area=maybe").status_code == 422
        unfiltered = JobPage.model_validate_json(client.get("/jobs?scope=all&activity=all").content)
        assert {job.external_id for job in unfiltered.items} == {"toronto", "elsewhere", "unclear"}
        for scope, total in (("eligible", 2), ("all", 3)):
            counts = client.get("/jobs/overview", params={"scope": scope}).json()
            assert counts["total"] == counts["statuses"]["new"] == total
        search = client.get("/jobs?scope=all&q=New%20Grad&activity=all").json()
        assert search["total"] == 0
    repeated = scrape_source(
        engine, ADAPTER, lambda _etag: FetchResult(data, None), normalizer=StubNormalizer()
    )
    assert repeated.created == 0 and repeated.unchanged == 3 and repeated.matched == 2


@pytest.mark.parametrize("field", ["is_canada_internship", "is_toronto_area"])
@pytest.mark.parametrize("invalid", ["true", 1])
def test_ai_booleans(field: str, invalid: object) -> None:
    job = normalized_listing().model_dump(include=set(ExtractedJob.model_fields))
    job[field] = invalid
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate({"jobs": [job]})
