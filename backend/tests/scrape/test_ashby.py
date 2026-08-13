import json

import httpx2

from job_backend.scrape.ashby import ashby
from job_backend.scrape.companies.company_sources import COMPANY_SOURCES
from job_backend.scrape.companies.models import Company


def company() -> Company:
    return Company(
        key="example",
        name="Example",
        careers_url="https://jobs.ashbyhq.com/example",
        job_board="ashby",
        board_name="example",
    )


def test_ashby_record() -> None:
    record = {
        "title": "Engineering Intern",
        "jobUrl": "https://jobs.ashbyhq.com/example/123",
        "applyUrl": "https://jobs.ashbyhq.com/example/123/application",
        "descriptionHtml": "<p>Python required; SQL preferred.</p>",
        "descriptionPlain": "Python required; SQL preferred.",
        "compensation": {"summary": "CAD 40 per hour"},
        "isListed": False,
        "secondaryLocations": [{"location": "Toronto"}],
        "employmentType": "Intern",
    }

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.params["includeCompensation"] == "true"
        assert request.headers["If-None-Match"] == '"old"'
        return httpx2.Response(200, json={"jobs": [record]}, headers={"etag": '"new"'})

    fetched = ashby.fetch_postings(company(), '"old"', transport=httpx2.MockTransport(handler))
    assert fetched.payload is not None and fetched.etag == '"new"'
    scraped = ashby.scrape_postings(company(), fetched.payload)
    assert scraped.fetched == 1
    document = scraped.documents[0]
    assert json.loads(document.content)["job"] == record
    assert document.external_id == document.application_url == record["jobUrl"]
    assert document.apply_url == record["applyUrl"]
    assert {"1password", "notion", "cohere", "ramp"} <= COMPANY_SOURCES.keys()
