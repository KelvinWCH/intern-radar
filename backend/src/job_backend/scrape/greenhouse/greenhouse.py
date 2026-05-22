from functools import partial

import httpx2
from pydantic import JsonValue, TypeAdapter, ValidationError

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


def feed_url(company: Company) -> str:
    if company.job_board != "greenhouse" or company.board_name is None:
        raise ValueError("A Greenhouse company and board_name are required")
    return f"https://boards-api.greenhouse.io/v1/boards/{company.board_name}/jobs?content=true"


def fetch_postings(
    company: Company, etag: str | None, *, transport: httpx2.BaseTransport | None = None
) -> FetchResult:
    return download_feed(feed_url(company), etag, accept="application/json", transport=transport)


def scrape_postings(company: Company, payload: bytes) -> ScrapeResult:
    try:
        envelope = TypeAdapter(dict[str, JsonValue]).validate_json(payload, strict=True)
        records = TypeAdapter(list[dict[str, JsonValue]]).validate_python(
            envelope.get("jobs"), strict=True
        )
        documents: list[RawDocument] = []
        for record in records:
            identifier = record.get("id")
            url = record.get("absolute_url")
            if (
                isinstance(identifier, bool)
                or not isinstance(identifier, int)
                or identifier <= 0
                or not isinstance(url, str)
            ):
                raise SourceDataError("Greenhouse posting requires an integer ID and absolute_url")
            if not isinstance(record.get("content"), str):
                raise SourceDataError(
                    "Greenhouse returned no full content; content=true is required"
                )
            documents.append(
                job_document(
                    company,
                    record,
                    feed_url=feed_url(company),
                    external_id=str(identifier),
                    application_url=url,
                    apply_url=url,
                )
            )
    except ValidationError:
        raise SourceDataError("Greenhouse returned malformed jobs or invalid HTTP URLs") from None
    return ScrapeResult(fetched=len(records), documents=documents)


def create_source(company: Company) -> JobSource:
    feed_url(company)
    return JobSource(
        name=company.source_name,
        fetch=partial(fetch_postings, company),
        scrape=partial(scrape_postings, company),
        complete_listing=True,
    )
