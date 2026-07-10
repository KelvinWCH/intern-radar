import json

import httpx2
from pydantic import JsonValue

from job_backend.scrape.companies.models import Company
from job_backend.scrape.hibob import hibob

POSTING_ID = "ce50ce64-bce7-40e5-8b07-362045e73ad1"


def _company() -> Company:
    return Company(
        key="xanadu",
        name="Xanadu",
        job_board="hibob",
        board_name="xanadu",
        careers_url="https://xanadu.careers.hibob.com/jobs",
    )


def _record() -> dict[str, JsonValue]:
    return {
        "id": POSTING_ID,
        "title": "Software Engineering Intern",
        "description": "<p>Complete work description.</p>",
        "requirements": "<p>Python.</p>",
        "responsibilities": "<p>Quantum software research.</p>",
        "benefits": "<p>Paid placement.</p>",
        "site": "Toronto",
        "country": "Canada",
        "publishedAt": "2026-10-01T12:00:00.123456789Z",
        "additionalMetadata": {"salary": [100, 200]},
    }


def _payload(records: list[dict[str, JsonValue]]) -> bytes:
    return json.dumps({"filterGroups": {}, "jobAdDetails": records}).encode()


def test_hibob_feed() -> None:
    def respond(request: httpx2.Request) -> httpx2.Response:
        assert request.method == "GET"
        assert str(request.url) == "https://xanadu.careers.hibob.com/api/job-ad"
        assert request.headers["companyIdentifier"] == "xanadu"
        assert request.headers["If-None-Match"] == '"previous"'
        return httpx2.Response(200, content=_payload([_record()]), headers={"ETag": '"current"'})

    fetched = hibob.fetch_postings(
        _company(), '"previous"', transport=httpx2.MockTransport(respond)
    )
    assert fetched.etag == '"current"'
    assert fetched.payload is not None
    scraped = hibob.scrape_postings(_company(), fetched.payload)
    assert scraped.fetched == 1
    document = scraped.documents[0]
    assert document.external_id == POSTING_ID
    assert document.application_url == f"https://xanadu.careers.hibob.com/jobs/{POSTING_ID}"
    assert document.apply_url == f"https://xanadu.careers.hibob.com/jobs/{POSTING_ID}/apply"
    assert json.loads(document.content)["job"] == _record()
