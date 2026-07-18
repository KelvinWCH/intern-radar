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
    if company.job_board != "lever" or company.board_name is None:
        raise ValueError("A Lever company and board_name are required")
    host = "api.eu.lever.co" if company.region == "eu" else "api.lever.co"
    return f"https://{host}/v0/postings/{company.board_name}?mode=json"


def fetch_postings(
    company: Company, etag: str | None, *, transport: httpx2.BaseTransport | None = None
) -> FetchResult:
    return download_feed(feed_url(company), etag, accept="application/json", transport=transport)


def scrape_postings(company: Company, payload: bytes) -> ScrapeResult:
    try:
        records = TypeAdapter(list[dict[str, JsonValue]]).validate_json(payload, strict=True)
        documents: list[RawDocument] = []
        for record in records:
            identifier = record.get("id")
            url = record.get("hostedUrl")
            apply_url = record.get("applyUrl")
            if (
                not isinstance(identifier, str)
                or not identifier.strip()
                or not isinstance(url, str)
            ):
                raise SourceDataError("Lever posting requires a string ID and hostedUrl")
            if apply_url is not None and not isinstance(apply_url, str):
                raise SourceDataError("Lever applyUrl must be a URL string or null")
            documents.append(
                job_document(
                    company,
                    record,
                    feed_url=feed_url(company),
                    external_id=identifier,
                    application_url=url,
                    apply_url=apply_url,
                )
            )
    except ValidationError:
        raise SourceDataError("Lever returned malformed job records or invalid HTTP URLs") from None
    return ScrapeResult(fetched=len(records), documents=documents)


def create_source(company: Company) -> JobSource:
    feed_url(company)
    return JobSource(
        name=company.source_name,
        fetch=partial(fetch_postings, company),
        scrape=partial(scrape_postings, company),
        complete_listing=True,
    )
