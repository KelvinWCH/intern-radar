from datetime import UTC, datetime

import httpx2
from pydantic import JsonValue

from job_backend.scrape.companies.models import Company
from job_backend.scrape.employmenthero import employmenthero

ORGANISATION_ID = "75a19b05-282e-414f-b507-6107f92dbf68"


def company() -> Company:
    return Company(
        key="amii",
        name="Amii",
        careers_url="https://www.amii.ca/about/career-opportunities",
        job_board="employmenthero",
        board_name=ORGANISATION_ID,
    )


def posting(identifier: str = "job-1") -> dict[str, JsonValue]:
    return {
        "id": identifier,
        "title": "Software Engineer",
        "application_url": f"https://jobs.employmenthero.com/jobs/{identifier}",
        "vendor_location_name": "Edmonton, Alberta",
        "created_at": "2025-10-15T01:14:51Z",
        "eoi": False,
        "hide_pay_rate": True,
        "salary_min": 1.0,
        "salary_max": 2.0,
        "custom_original": {"text": "Preserve this complete upstream field."},
    }


def page(
    records: list[dict[str, JsonValue]],
    *,
    index: int = 1,
    pages: int = 1,
    total: int | None = None,
) -> dict[str, JsonValue]:
    data: dict[str, JsonValue] = {
        "items": [record for record in records],
        "item_per_page": 2,
        "page_index": index,
        "total_pages": pages,
        "total_items": len(records) if total is None else total,
    }
    return {"data": data}


def test_pagination() -> None:
    first, second = posting(), posting("job-2")
    second["eoi"] = True
    visited: list[int] = []

    def feed(request: httpx2.Request) -> httpx2.Response:
        assert request.url.host == "ats-cdn.ehrocks.com"
        assert ORGANISATION_ID in request.url.path
        assert "if-none-match" not in request.headers
        index = int(request.url.params["page_index"])
        visited.append(index)
        return httpx2.Response(
            200,
            json=page([first] if index == 1 else [second], index=index, pages=2, total=2),
        )

    downloaded = employmenthero.fetch_postings(
        company(), '"stale"', transport=httpx2.MockTransport(feed)
    )
    assert downloaded.payload is not None and downloaded.etag is None
    discovered = employmenthero.scrape_postings(downloaded.payload)
    assert visited == [1, 2]
    assert discovered.fetched == 2 and discovered.documents == []
    assert discovered.links[0].external_id == "job-1"
    assert discovered.links[0].listing_data["employmenthero"] == first
    assert discovered.links[0].listing_data["location"] == "Edmonton, Alberta"
    assert discovered.links[0].date_posted == int(
        datetime(2025, 10, 15, 1, 14, 51, tzinfo=UTC).timestamp()
    )
    assert discovered.links[1].date_posted is None
    source = employmenthero.create_source(company())
    assert source.links_are_apply_urls is False
    assert source.require_recent_dates is False
    assert source.page_renderer == "auto"
