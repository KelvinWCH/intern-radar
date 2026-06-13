from functools import partial

import httpx2
from pydantic import JsonValue, ValidationError

from job_backend.scrape.companies.documents import job_document
from job_backend.scrape.companies.models import Company
from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.pipeline.models import (
    FetchResult,
    JobSource,
    RawDocument,
    ScrapeResult,
)
from job_backend.scrape.utils.http import download_feed
from job_backend.scrape.workable.constants import API_ROOT, MAX_RESPONSE_BYTES, PLACE_FIELDS
from job_backend.scrape.workable.models import WorkableFeed, WorkablePosting


def feed_url(company: Company) -> str:
    if company.job_board != "workable" or company.board_name is None:
        raise ValueError("A Workable company and board_name are required")
    return f"{API_ROOT}/{company.board_name}?details=true"


def fetch_postings(
    company: Company, etag: str | None, *, transport: httpx2.BaseTransport | None = None
) -> FetchResult:
    return download_feed(
        feed_url(company),
        etag,
        max_bytes=MAX_RESPONSE_BYTES,
        accept="application/json",
        transport=transport,
    )


def _without_place(record: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {key: value for key, value in record.items() if key not in PLACE_FIELDS}


def scrape_postings(company: Company, payload: bytes) -> ScrapeResult:
    try:
        feed = WorkableFeed.model_validate_json(payload, strict=True)
        records: dict[str, dict[str, JsonValue]] = {}
        for record in feed.jobs:
            posting = WorkablePosting.model_validate(record)
            previous = records.get(posting.shortcode)
            if previous is None:
                records[posting.shortcode] = dict(record)
                continue
            if _without_place(previous) != _without_place(record):
                raise SourceDataError("Workable returned duplicate posting shortcodes")
            places = previous.get("locations")
            extra = record.get("locations")
            if isinstance(places, list) and isinstance(extra, list):
                previous["locations"] = [
                    *places,
                    *(place for place in extra if place not in places),
                ]
        documents: list[RawDocument] = []
        for shortcode, record in records.items():
            posting = WorkablePosting.model_validate(record)
            documents.append(
                job_document(
                    company,
                    record,
                    feed_url=feed_url(company),
                    external_id=shortcode,
                    application_url=posting.url,
                    apply_url=posting.application_url,
                )
            )
    except ValidationError:
        raise SourceDataError(
            "Workable returned malformed jobs, missing descriptions, or a challenge response"
        ) from None
    return ScrapeResult(fetched=len(records), documents=documents)


def create_source(company: Company) -> JobSource:
    feed_url(company)
    return JobSource(
        name=company.source_name,
        fetch=partial(fetch_postings, company),
        scrape=partial(scrape_postings, company),
        complete_listing=True,
    )
