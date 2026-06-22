import json
import time
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from job_backend.common.models import AiSettings
from job_backend.jobs.models import Job
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.scrape.control.catalog import build_scrape_command
from job_backend.scrape.control.models import ScrapeRequest
from job_backend.scrape.github.github_sources.simplify_internships import ADAPTER
from job_backend.scrape.pipeline.heuristics.classification import (
    classify_locations,
    internship_title,
)
from job_backend.scrape.pipeline.models import FetchResult, RawDocument
from job_backend.scrape.pipeline.pipeline import scrape_source
from tests.helpers import listing, payload


@pytest.mark.parametrize(
    "title", ["Software Engineering Intern", "SWE Co-op", "Stagiaire en informatique"]
)
def test_internship_title_variants(title: str) -> None:
    assert internship_title(title)


@pytest.mark.parametrize(
    "title", ["Internal Auditor", "Internship Program Manager", "Senior Software Engineer"]
)
def test_non_internship_titles(title: str) -> None:
    assert not internship_title(title)


@pytest.mark.parametrize(
    ("locations", "expected"),
    [
        (["Toronto, ON"], (True, True)),
        (["Tornto, Ontario"], (True, True)),
        (["Montréal, QC"], (True, False)),
        (["San Francisco, CA"], (False, False)),
    ],
)
def test_location_matching(locations: list[str], expected: tuple[bool, bool]) -> None:
    assert classify_locations(locations) == expected


def test_default_scrape_no_ai(
    engine: Database,
    monkeypatch: MonkeyPatch,
) -> None:
    def forbid_ai() -> AiSettings:
        raise AssertionError("A default scrape must never read AI settings")

    calls: list[str] = []
    page_text = "Responsibilities\nBuild useful tools.\nRequirements\nPython.\nPay\n$35/hour."

    def read_page(url: str) -> RawDocument:
        calls.append(url)
        return RawDocument(content=page_text, source_url=url)

    monkeypatch.setattr(AiSettings, "from_environment", forbid_ai)
    row = listing()
    row["date_posted"] = int(time.time()) - 60
    result = scrape_source(
        engine, ADAPTER, lambda _etag: FetchResult(payload(row), None), fetch_page=read_page
    )
    assert result.created == 1
    assert result.input_tokens == result.output_tokens == 0
    assert result.performance is not None and result.performance.ai_calls == 0
    assert len(calls) == 1
    with Session(engine) as session:
        job = session.all(Job)[0]
        assert job.title == row["title"] and job.is_toronto_area
        assert job.raw_description == page_text
        assert job.raw_payload is not None and job.raw_payload["listing_data"] == row
        job.summary = "Previously enriched summary"
        job.source_job_id = "employer-123"
        job.raw_description = json.dumps(row)
        session.commit()
    row["title"] = "Software Engineering Co-op"
    scrape_source(
        engine, ADAPTER, lambda _etag: FetchResult(payload(row), None), fetch_page=read_page
    )
    with Session(engine) as session:
        job = session.all(Job)[0]
        assert job.title == row["title"]
        assert job.summary == "Previously enriched summary" and job.source_job_id == "employer-123"
        assert job.raw_description == page_text


def test_ai_requires_an_explicit_request(tmp_path: Path) -> None:
    request = ScrapeRequest(
        request_id="12345678-1234-1234-1234-123456789abc", sources=["github:simplify-summer2027"]
    )
    assert not request.use_ai and "--use-ai" not in build_scrape_command(request, tmp_path)
    request.use_ai = True
    assert "--use-ai" in build_scrape_command(request, tmp_path)
