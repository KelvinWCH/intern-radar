from functools import partial
from urllib.parse import quote

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
    if company.job_board != "ashby" or company.board_name is None:
        raise ValueError("An Ashby company and board_name are required")
    board = quote(company.board_name, safe="")
    return f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true"


def fetch_postings(
    company: Company,
    etag: str | None,
    *,
    transport: httpx2.BaseTransport | None = None,
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
            url, apply_url = record.get("jobUrl"), record.get("applyUrl")
            if not isinstance(url, str) or not url:
                raise SourceDataError("Ashby posting requires jobUrl")
            if apply_url is not None and not isinstance(apply_url, str):
                raise SourceDataError("Ashby applyUrl must be a URL or null")
            if not any(
                isinstance(record.get(key), str) and record.get(key)
                for key in ("descriptionHtml", "descriptionPlain")
            ):
                raise SourceDataError("Ashby posting has no full description")
            documents.append(
                job_document(
                    company,
                    record,
                    feed_url=feed_url(company),
                    external_id=url,
                    application_url=url,
                    apply_url=apply_url,
                )
            )
    except ValidationError:
        raise SourceDataError("Ashby returned malformed jobs or invalid HTTP URLs") from None
    return ScrapeResult(fetched=len(records), documents=documents)


def create_source(company: Company) -> JobSource:
    feed_url(company)
    return JobSource(
        name=company.source_name,
        fetch=partial(fetch_postings, company),
        scrape=partial(scrape_postings, company),
        complete_listing=True,
    )
