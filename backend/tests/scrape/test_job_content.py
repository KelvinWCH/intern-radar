import json
import time
from pathlib import Path

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import JsonValue, TypeAdapter

from job_backend.common.models import AiSettings
from job_backend.jobs.models import Job, JobResponse
from job_backend.main import create_app
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.scrape.pipeline.ai import AiNormalizer
from job_backend.scrape.pipeline.models import (
    ExtractedJob,
    ExtractionResult,
    FetchResult,
    JobLink,
    JobSource,
    RawDocument,
    ScrapeResult,
)
from job_backend.scrape.pipeline.pipeline import scrape_source
from tests.helpers import normalized_listing, qualifications

JOB_URL = "https://jobs.lever.co/fictional/00000001-0000-4000-8000-000000000001"
FULL_PAGE = """Fictional Safety Intern, Toronto.
Responsibilities: build Python tools and analyze large collision datasets.
Qualifications: third-year Computer Science undergraduate; Python and NumPy required.
Bonus: SQL and dashboards.
Pay: CAD 40 per hour.
Benefits: meals and team events.
Please include your transcript.
"""


@pytest.mark.parametrize("short_link", [False, True])
def test_full_page_kept(engine: Database, short_link: bool) -> None:
    initial_url = "https://example.com/redirect" if short_link else JOB_URL + "/apply"
    link = JobLink(
        url=initial_url,
        listing_url="https://example.com/jobs.json",
        external_id="repository-row",
        date_posted=int(time.time()) - 3600,
    )
    source = JobSource(
        name="fictional-content",
        fetch=lambda _etag: FetchResult(b"links", None),
        scrape=lambda _raw: ScrapeResult(1, links=[link]),
    )
    requirements = qualifications().model_dump(mode="json")
    education = requirements["education"]
    education["degree_levels"] = ["Bachelor's"]
    education["fields_of_study"] = ["Computer Science"]
    education["year_of_study_required"] = 3
    requirements.update(
        required_skills=["Python", "Data analysis"],
        preferred_skills=["SQL", "Dashboards"],
        tech_stack=["Python", "NumPy", "SQL"],
        other_requirements=["Include academic transcript"],
    )
    extracted = ExtractedJob.model_validate(
        {
            **normalized_listing().model_dump(
                exclude={"source", "external_id", "source_url", "raw_payload", "raw_description"}
            ),
            "application_url": JOB_URL,
            "apply_url": None,
            "summary": "Build Python tools for safety data analysis.",
            "qualifications": requirements,
        }
    )
    calls: list[str] = []

    def read(url: str) -> RawDocument:
        calls.append(url)
        if url == "https://example.com/redirect":
            return RawDocument(content="Short form preview", source_url=JOB_URL + "/apply")
        assert url == JOB_URL
        return RawDocument(content=FULL_PAGE, source_url=JOB_URL)

    def respond(request: httpx2.Request) -> httpx2.Response:
        data = TypeAdapter(dict[str, JsonValue]).validate_json(request.content)
        messages = TypeAdapter(list[dict[str, str]]).validate_python(data["messages"])
        document = TypeAdapter(dict[str, JsonValue]).validate_json(messages[-1]["content"])
        assert document["content"] == FULL_PAGE
        assert document["apply_url"] == JOB_URL + "/apply"
        result = ExtractionResult(jobs=[extracted])
        return httpx2.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": result.model_dump_json()}, "finish_reason": "stop"}
                ]
            },
        )

    normalizer = AiNormalizer(
        AiSettings(base_url="http://localhost/v1", model="fictional"),
        httpx2.MockTransport(respond),
    )
    run = scrape_source(engine, source, normalizer=normalizer, fetch_page=read)
    assert run.created == 1
    assert calls == ([initial_url, JOB_URL] if short_link else [JOB_URL])
    with Session(engine) as session:
        saved = session.find(Job).first()
        assert saved is not None
        response = JobResponse.model_validate(saved)
        assert response.raw_description == FULL_PAGE
        assert response.summary == extracted.summary
        assert response.qualifications is not None
        assert response.qualifications.education.year_of_study_required == 3
        assert response.qualifications.tech_stack == ["NumPy", "Python", "SQL"]
        assert saved.external_id == "repository-row"
        job_id = saved.id
    assert engine.local_path is not None
    with TestClient(create_app(Path(engine.local_path))) as client:
        result = client.get(f"/jobs/{job_id}")
        assert result.status_code == 200
        response = JobResponse.model_validate_json(result.content)
        assert response.raw_description == FULL_PAGE
        assert response.application_url == JOB_URL and response.apply_url == JOB_URL + "/apply"
        assert "description" not in json.loads(result.content)
        assert "degrees" not in json.loads(result.content)
