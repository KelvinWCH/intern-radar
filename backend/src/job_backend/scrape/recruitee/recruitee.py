from functools import partial

import httpx2
from pydantic import ValidationError

from job_backend.scrape.companies.documents import job_document
from job_backend.scrape.companies.models import Company
from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.pipeline.models import (
    FetchResult,
    JobSource,
    RawDocument,
    ScrapeResult,
)
from job_backend.scrape.recruitee.constants import (
    API_HOST_SUFFIX,
    MAX_RESPONSE_BYTES,
    OFFERS_PATH,
)
from job_backend.scrape.recruitee.models import RecruiteeFeed, RecruiteeOffer
from job_backend.scrape.utils.http import download_feed


def feed_url(company: Company) -> str:
    if company.job_board != "recruitee" or company.board_name is None:
        raise ValueError("A Recruitee company and board_name are required")
    return f"https://{company.board_name}{API_HOST_SUFFIX}{OFFERS_PATH}"


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


def scrape_postings(company: Company, payload: bytes) -> ScrapeResult:
    try:
        feed = RecruiteeFeed.model_validate_json(payload, strict=True)
        documents: list[RawDocument] = []
        identifiers: set[int] = set()
        for record in feed.offers:
            offer = RecruiteeOffer.model_validate(record)
            if offer.id in identifiers:
                raise SourceDataError("Recruitee returned duplicate offer IDs")
            identifiers.add(offer.id)
            documents.append(
                job_document(
                    company,
                    record,
                    feed_url=feed_url(company),
                    external_id=str(offer.id),
                    application_url=offer.careers_url,
                    apply_url=offer.careers_apply_url,
                )
            )
    except ValidationError:
        raise SourceDataError("Recruitee returned malformed offers or invalid URLs") from None
    return ScrapeResult(fetched=len(feed.offers), documents=documents)


def create_source(company: Company) -> JobSource:
    feed_url(company)
    return JobSource(
        name=company.source_name,
        fetch=partial(fetch_postings, company),
        scrape=partial(scrape_postings, company),
        complete_listing=True,
    )
