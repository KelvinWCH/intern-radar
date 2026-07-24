import json

import httpx2
from pydantic import JsonValue

from job_backend.scrape.companies.models import Company
from job_backend.scrape.workable import workable


def _company() -> Company:
    return Company(
        key="example",
        name="Example",
        job_board="workable",
        board_name="example",
        careers_url="https://apply.workable.com/example/",
    )


def _record() -> dict[str, JsonValue]:
    return {
        "shortcode": "ABC123",
        "code": None,
        "title": "Software Engineering Intern",
        "description": "<p>Duties</p><h2>Requirements</h2><p>Python</p><h2>Benefits</h2><p>Pay</p>",
        "url": "https://apply.workable.com/j/ABC123",
        "application_url": "https://apply.workable.com/j/ABC123/apply",
        "published_on": "2026-10-01",
        "locations": [
            {"city": "Toronto", "region": "Ontario", "country": "Canada", "countryCode": "CA"},
            {"city": "Los Angeles", "region": "CA", "countryCode": "US"},
        ],
        "unknownField": {"salary": [100, 200]},
    }


def test_workable_feed() -> None:
    def respond(request: httpx2.Request) -> httpx2.Response:
        assert request.method == "GET"
        assert str(request.url) == (
            "https://apply.workable.com/api/v1/widget/accounts/example?details=true"
        )
        assert request.headers["if-none-match"] == '"previous"'
        return httpx2.Response(200, json={"name": "Example", "jobs": [_record()]})

    fetched = workable.fetch_postings(
        _company(), '"previous"', transport=httpx2.MockTransport(respond)
    )
    assert fetched.payload is not None
    scraped = workable.scrape_postings(_company(), fetched.payload)
    assert scraped.fetched == 1
    document = scraped.documents[0]
    assert document.external_id == "ABC123"
    assert document.application_url == "https://apply.workable.com/j/ABC123"
    assert document.apply_url == "https://apply.workable.com/j/ABC123/apply"
    assert json.loads(document.content)["job"] == _record()
