import json
from datetime import UTC, datetime

import pytest
from pydantic import JsonValue

from job_backend.scrape.companies.models import Company
from job_backend.scrape.lever import lever
from job_backend.scrape.pipeline.heuristics.normalizer import HeuristicNormalizer


@pytest.mark.parametrize("region", ["global", "eu"])
def test_lever_locations_and_date(region: str) -> None:
    company = Company.model_validate(
        {
            "key": "fictional",
            "name": "Example Company",
            "careers_url": "https://jobs.lever.co/fictional",
            "job_board": "lever",
            "board_name": "fictional",
            "region": region,
        }
    )
    timestamp = int(datetime(2025, 10, 15, 12, tzinfo=UTC).timestamp())
    record: dict[str, JsonValue] = {
        "id": "job-123",
        "text": "Software Engineering Intern",
        "createdAt": timestamp * 1000,
        "country": "US",
        "categories": {
            "location": "San Francisco, CA",
            "allLocations": ["San Francisco, CA", "Toronto, ON", "Vancouver, BC"],
        },
        "description": "Build reliable infrastructure and developer tools.",
        "hostedUrl": "https://jobs.lever.co/fictional/job-123",
        "applyUrl": "https://jobs.lever.co/fictional/job-123/apply",
    }
    document = lever.scrape_postings(company, json.dumps([record]).encode()).documents[0]
    job = HeuristicNormalizer().extract(document).jobs[0]
    assert job.date_posted == timestamp
    assert job.locations == ["San Francisco, CA, United States", "Toronto, ON", "Vancouver, BC"]
    assert job.is_canada_internship and job.is_toronto_area
    assert job.source_job_id == "job-123"
    assert json.loads(document.content)["job"] == record
