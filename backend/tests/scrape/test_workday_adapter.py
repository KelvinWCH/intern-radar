import json

import httpx2
import pytest
from pydantic import JsonValue

from job_backend.scrape.companies.models import Company
from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.workday import workday


def _company() -> Company:
    return Company(
        key="example",
        name="Example",
        job_board="workday",
        board_name="Careers",
        careers_url="https://example.wd5.myworkdayjobs.com/en-US/Careers",
    )


def _listing(identifier: str) -> dict[str, JsonValue]:
    return {
        "title": "Software Engineering Intern",
        "externalPath": f"/job/Toronto/Software-Engineering-Intern_{identifier}",
        "bulletFields": [identifier],
        "unknownListingField": {"retain": True},
    }


def _detail(identifier: str) -> dict[str, JsonValue]:
    return {
        "jobPostingInfo": {
            "id": f"posting-{identifier}",
            "jobReqId": identifier,
            "title": "Software Engineering Intern",
            "jobDescription": "<p>Complete duties, requirements, salary, and benefits.</p>",
            "location": "Toronto",
            "country": {"descriptor": "Canada"},
            "additionalLocations": ["United States, CA, Remote"],
            "externalUrl": f"https://example.wd5.myworkdayjobs.com/Careers/job/Toronto/{identifier}",
            "startDate": "2026-10-01",
        },
        "hiringOrganization": {"name": "Example Canada"},
        "unknownDetailField": {"preserved": [1, 2]},
    }


def test_workday_canada_facet() -> None:
    details: list[str] = []
    filtered_offsets: list[int] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        if request.method == "POST":
            body = json.loads(request.content)
            filters = body["appliedFacets"]
            if not filters:
                return httpx2.Response(
                    200,
                    json={
                        "total": 5000,
                        "jobPostings": [_listing("irrelevant-root")],
                        "facets": [
                            {
                                "facetParameter": "locationMainGroup",
                                "values": [
                                    {
                                        "facetParameter": "locationHierarchy1",
                                        "values": [
                                            {
                                                "descriptor": "Canada",
                                                "id": "provider-canada",
                                                "count": 3,
                                            },
                                            {
                                                "descriptor": "United States",
                                                "id": "provider-us",
                                                "count": 4997,
                                            },
                                        ],
                                    }
                                ],
                            }
                        ],
                    },
                )
            assert filters == {"locationHierarchy1": ["provider-canada"]}
            filtered_offsets.append(body["offset"])
            records = (
                [
                    {**_listing("senior"), "title": "Senior Engineer", "locationsText": "Toronto"},
                    {**_listing("foreign"), "locationsText": "Austin, TX, USA"},
                    _listing("intern"),
                ]
                if body["offset"] == 0
                else []
            )
            return httpx2.Response(200, json={"total": 3, "jobPostings": records})
        identifier = request.url.path.rsplit("_", 1)[-1]
        details.append(identifier)
        return httpx2.Response(200, json=_detail(identifier))

    fetched = workday.fetch_postings(_company(), None, transport=httpx2.MockTransport(respond))
    assert fetched.payload is not None and not fetched.failures
    assert details == ["intern"] and filtered_offsets == [0, 3]
    scraped = workday.scrape_postings(_company(), fetched.payload)
    assert scraped.fetched == 3
    assert [document.external_id for document in scraped.documents] == ["posting-intern"]
    assert sorted(scraped.listed_urls) == [
        "https://example.wd5.myworkdayjobs.com/Careers/job/Toronto/Software-Engineering-Intern_foreign",
        "https://example.wd5.myworkdayjobs.com/Careers/job/Toronto/Software-Engineering-Intern_senior",
    ]


def test_workday_student_details() -> None:
    details: list[str] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        if request.method == "POST":
            body = json.loads(request.content)
            records = (
                [
                    {**_listing("dev"), "title": "Software Developer"},
                    {**_listing("coop"), "title": "Data Analyst Co-op (Winter 2027)"},
                    {key: value for key, value in _listing("untitled").items() if key != "title"},
                ]
                if body["offset"] == 0
                else []
            )
            return httpx2.Response(200, json={"total": 3, "jobPostings": records})
        identifier = request.url.path.rsplit("_", 1)[-1]
        details.append(identifier)
        return httpx2.Response(200, json=_detail(identifier))

    fetched = workday.fetch_postings(_company(), None, transport=httpx2.MockTransport(respond))
    assert sorted(details) == ["coop", "untitled"]
    assert fetched.payload is not None and fetched.etag is not None
    scraped = workday.scrape_postings(_company(), fetched.payload)
    assert scraped.fetched == 3
    assert sorted(document.external_id or "" for document in scraped.documents) == [
        "posting-coop",
        "posting-untitled",
    ]
    assert scraped.listed_urls == (
        "https://example.wd5.myworkdayjobs.com/Careers/job/Toronto/Software-Engineering-Intern_dev",
    )
    only_listed = json.dumps([{"listing": {**_listing("dev"), "title": "Analyst"}}]).encode()
    assert workday.scrape_postings(_company(), only_listed).documents == []


@pytest.mark.parametrize(
    "body",
    [
        {"errors": ["access denied"]},
        {"total": 2, "jobPostings": []},
        {"total": 1, "jobPostings": [{"title": "Intern", "externalPath": "//evil.test/job/1"}]},
    ],
)
def test_workday_bad_listing(body: dict[str, JsonValue]) -> None:
    transport = httpx2.MockTransport(lambda _: httpx2.Response(200, json=body))
    with pytest.raises(SourceDataError):
        workday.fetch_postings(_company(), None, transport=transport)


@pytest.mark.parametrize("status_code", [429, 520])
def test_workday_retry_after(monkeypatch: pytest.MonkeyPatch, status_code: int) -> None:
    delays: list[float] = []
    attempts = 0
    monkeypatch.setattr(workday.time, "sleep", delays.append)

    def respond(_: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx2.Response(status_code, headers={"Retry-After": "12"})
        return httpx2.Response(200, json={"total": 0, "jobPostings": []})

    fetched = workday.fetch_postings(_company(), None, transport=httpx2.MockTransport(respond))
    assert fetched.payload == b"[]"
    assert delays == [12]
    assert attempts == 2
