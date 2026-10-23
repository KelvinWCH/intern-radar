from functools import partial
from uuid import UUID

import httpx2
from pydantic import JsonValue, TypeAdapter, ValidationError

from job_backend.scrape.companies.models import Company
from job_backend.scrape.employmenthero.constants import (
    API_ROOT,
    MAX_JOBS,
    MAX_PAGE_BYTES,
    MAX_PAGES,
    MAX_TOTAL_BYTES,
)
from job_backend.scrape.employmenthero.models import (
    EmploymentHeroPosting,
    EmploymentHeroResponse,
)
from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.github.utils.dates import parse_posted_date
from job_backend.scrape.pipeline.models import (
    FetchResult,
    JobLink,
    JobSource,
    ScrapeResult,
)
from job_backend.scrape.utils.http import download_feed


def feed_url(company: Company, page_index: int = 1) -> str:
    if company.job_board != "employmenthero" or company.board_name is None:
        raise ValueError("An EmploymentHero company and organisation UUID are required")
    organisation_id = str(UUID(company.board_name))
    if page_index < 1:
        raise ValueError("EmploymentHero page_index must be positive")
    return f"{API_ROOT}/{organisation_id}/jobs?page_index={page_index}"


def _job_link(company: Company, record: dict[str, JsonValue]) -> JobLink:
    posting = EmploymentHeroPosting.model_validate(record)
    return JobLink(
        url=posting.application_url,
        listing_url=company.careers_url,
        external_id=posting.id,
        date_posted=None if posting.eoi else parse_posted_date(posting.created_at),
        listing_data={
            "company": company.name,
            "title": posting.title,
            "location": posting.vendor_location_name,
            "source_job_id": posting.id,
            "employmenthero": record,
        },
    )


def fetch_postings(
    company: Company,
    _etag: str | None,
    *,
    transport: httpx2.BaseTransport | None = None,
) -> FetchResult:
    links: list[JobLink] = []
    identifiers: set[str] = set()
    urls: set[str] = set()
    total_bytes = 0
    expected_items: int | None = None
    expected_pages: int | None = None
    try:
        for page_index in range(1, MAX_PAGES + 1):
            downloaded = download_feed(
                feed_url(company, page_index),
                None,
                max_bytes=MAX_PAGE_BYTES,
                accept="application/json",
                transport=transport,
            )
            if downloaded.payload is None:
                raise SourceDataError("EmploymentHero returned an unexpected unchanged page")
            total_bytes += len(downloaded.payload)
            if total_bytes > MAX_TOTAL_BYTES:
                raise SourceDataError("EmploymentHero feed exceeds the total byte limit")
            page = EmploymentHeroResponse.model_validate_json(downloaded.payload).data
            if expected_items is None:
                expected_items, expected_pages = page.total_items, page.total_pages
            if page.total_items > MAX_JOBS or page.total_pages > MAX_PAGES:
                raise SourceDataError("EmploymentHero feed exceeds configured collection limits")
            if (
                page.page_index != page_index
                or page.total_items != expected_items
                or page.total_pages != expected_pages
                or len(page.items) > page.item_per_page
                or (page.total_items > 0 and (not page.items or page.total_pages < page_index))
                or (page.total_items == 0 and (page.items or page.total_pages > 1))
            ):
                raise SourceDataError("EmploymentHero returned inconsistent pagination")
            for record in page.items:
                link = _job_link(company, record)
                if link.external_id is None:
                    raise SourceDataError("EmploymentHero job is missing its identifier")
                if link.external_id in identifiers or link.url in urls:
                    raise SourceDataError("EmploymentHero repeated a job across result pages")
                identifiers.add(link.external_id)
                urls.add(link.url)
                links.append(link)
            if len(links) > page.total_items:
                raise SourceDataError("EmploymentHero returned more jobs than its declared total")
            if page_index >= page.total_pages:
                if len(links) != page.total_items:
                    raise SourceDataError("EmploymentHero returned an incomplete listing")
                return FetchResult(TypeAdapter(list[JobLink]).dump_json(links), None)
    except ValidationError:
        raise SourceDataError(
            "EmploymentHero returned malformed pagination or job records"
        ) from None
    raise SourceDataError("EmploymentHero pagination exceeded the page limit")


def scrape_postings(payload: bytes) -> ScrapeResult:
    try:
        links = TypeAdapter(list[JobLink]).validate_json(payload, strict=True)
    except ValidationError:
        raise SourceDataError("EmploymentHero returned malformed discovered job links") from None
    return ScrapeResult(fetched=len(links), links=links)


def create_source(company: Company) -> JobSource:
    feed_url(company)
    return JobSource(
        name=company.source_name,
        fetch=partial(fetch_postings, company),
        scrape=scrape_postings,
        require_recent_dates=False,
        links_are_apply_urls=False,
        page_renderer="auto",
    )
