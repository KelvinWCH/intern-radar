import json
from pathlib import Path
from typing import Literal

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import JsonValue, TypeAdapter

from job_backend.common.models import AiSettings
from job_backend.jobs.models import Job, JobResponse
from job_backend.main import create_app
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.scrape.companies.models import Company
from job_backend.scrape.greenhouse import greenhouse
from job_backend.scrape.lever import lever
from job_backend.scrape.pipeline.ai import AiNormalizer
from job_backend.scrape.pipeline.models import (
    ExtractedJob,
    ExtractionResult,
    FetchResult,
)
from job_backend.scrape.pipeline.pipeline import scrape_source
from tests.helpers import ADAPTER, StubNormalizer, listing, normalized_listing, payload


@pytest.mark.parametrize("provider", ["lever", "greenhouse"])
def test_company_feed_record(engine: Database, provider: Literal["lever", "greenhouse"]) -> None:
    company = Company(
        key="fictional",
        name="Example Company",
        careers_url="https://example.com/careers",
        job_board=provider,
        board_name="fictional",
    )
    job_url = "https://example.com/jobs/known"
    github_row = listing("github-row")
    github_row["url"] = job_url
    first = scrape_source(
        engine,
        ADAPTER,
        lambda _etag: FetchResult(payload(github_row), None),
        normalizer=StubNormalizer(),
    )
    assert first.created == 1
    module = lever if provider == "lever" else greenhouse
    record: dict[str, JsonValue] = {
        "id": "upstream-123" if provider == "lever" else 123,
        "description": "Build Python tools.",
        "lists": [{"text": "Qualifications", "content": "Python and SQL required."}],
        "additional": "Bonus: dashboards. Benefits: meals. CAD 40/hour.",
    }
    if provider == "lever":
        record.update(hostedUrl=job_url, applyUrl=job_url + "/apply")
        upstream: JsonValue = [record]
    else:
        record.update(absolute_url=job_url, content="<h2>Requirements</h2><p>Python and SQL</p>")
        upstream = {"jobs": [record]}
    source = module.create_source(company)
    snapshot = json.dumps(upstream).encode()

    def feed(request: httpx2.Request) -> httpx2.Response:
        assert str(request.url) == module.feed_url(company)
        assert request.headers["If-None-Match"] == '"old"'
        if provider == "greenhouse":
            assert request.url.params["content"] == "true"
        return httpx2.Response(200, content=snapshot, headers={"ETag": '"new"'})

    downloaded = module.fetch_postings(company, '"old"', transport=httpx2.MockTransport(feed))
    assert downloaded.payload == snapshot
    expected_apply = job_url + "/apply" if provider == "lever" else job_url
    data = normalized_listing().model_dump(
        exclude={"source", "external_id", "source_url", "raw_payload", "raw_description"}
    )
    data.update(
        source_job_id="REQ-123", application_url=job_url, summary="Work with Python and SQL."
    )
    extracted = ExtractedJob.model_validate(data)

    def ai(request: httpx2.Request) -> httpx2.Response:
        body = TypeAdapter(dict[str, JsonValue]).validate_json(request.content)
        messages = TypeAdapter(list[dict[str, str]]).validate_python(body["messages"])
        document = TypeAdapter(dict[str, JsonValue]).validate_json(messages[-1]["content"])
        assert isinstance(document["content"], str)
        original = TypeAdapter(dict[str, JsonValue]).validate_json(document["content"])
        assert original["job"] == record and original["company_name"] == company.name
        assert document["apply_url"] == expected_apply
        return httpx2.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": ExtractionResult(jobs=[extracted]).model_dump_json()
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    normalizer = AiNormalizer(
        AiSettings(base_url="http://localhost/v1", model="fictional"), httpx2.MockTransport(ai)
    )
    result = scrape_source(engine, source, lambda _etag: downloaded, normalizer=normalizer)
    assert result.created == 1 and result.updated == 0
    with Session(engine) as session:
        assert len(session.find(Job)) == 2
        job = session.find(Job, where=lambda row: row.source == source.name).first()
        assert job is not None and job.external_id == str(record["id"])
        assert job.raw_description is not None
        assert json.loads(job.raw_description)["job"] == record
        assert job.raw_payload is not None and job.raw_payload["job"] == record
        assert job.apply_url == expected_apply
        job_id = job.id
    assert engine.local_path is not None
    with TestClient(create_app(Path(engine.local_path))) as client:
        response = client.get(f"/jobs/{job_id}")
        assert response.status_code == 200
        saved = JobResponse.model_validate_json(response.content)
        assert saved.qualifications is not None
        assert saved.qualifications.education.degree_levels == ["Bachelor's"]
        assert saved.raw_description is not None and "Benefits: meals" in saved.raw_description
