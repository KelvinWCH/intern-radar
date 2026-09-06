import re
from functools import partial
from urllib.parse import urlsplit

import httpx2
from pydantic import ValidationError

from job_backend.scrape.companies.documents import job_document
from job_backend.scrape.companies.models import Company
from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.hibob.constants import (
    BOARD_NAME_PATTERN,
    CAREERS_HOST_SUFFIX,
    COMPANY_HEADER,
    MAX_RESPONSE_BYTES,
    PUBLIC_FEED_PATH,
)
from job_backend.scrape.hibob.models import HiBobFeed, HiBobPosting
from job_backend.scrape.pipeline.models import (
    FetchResult,
    JobSource,
    RawDocument,
    ScrapeResult,
)
from job_backend.scrape.utils.constants import IMPORTER_USER_AGENT, REQUEST_TIMEOUT
from job_backend.scrape.utils.pacing import pace_request, track_response


def board_url(company: Company) -> str:
    board_name = company.board_name
    parts = urlsplit(company.careers_url)
    if (
        company.job_board != "hibob"
        or board_name is None
        or re.fullmatch(BOARD_NAME_PATTERN, board_name) is None
        or parts.scheme != "https"
        or parts.hostname != f"{board_name}{CAREERS_HOST_SUFFIX}"
        or parts.port not in {None, 443}
        or parts.username is not None
        or parts.password is not None
        or parts.path.rstrip("/") not in {"", "/jobs"}
        or parts.query
        or parts.fragment
    ):
        raise ValueError("HiBob requires its matching public company subdomain and careers URL")
    return f"https://{board_name}{CAREERS_HOST_SUFFIX}"


def feed_url(company: Company) -> str:
    return f"{board_url(company)}{PUBLIC_FEED_PATH}"


def fetch_postings(
    company: Company, etag: str | None, *, transport: httpx2.BaseTransport | None = None
) -> FetchResult:
    url = feed_url(company)
    headers = {
        "Accept": "application/json",
        "User-Agent": IMPORTER_USER_AGENT,
        COMPANY_HEADER: company.board_name or "",
    }
    if etag:
        headers["If-None-Match"] = etag
    with (
        httpx2.Client(
            transport=transport,
            timeout=REQUEST_TIMEOUT,
            event_hooks={"request": [pace_request], "response": [track_response]},
        ) as client,
        client.stream("GET", url, headers=headers) as response,
    ):
        if response.status_code == 304:
            return FetchResult(payload=None, etag=etag)
        response.raise_for_status()
        chunks: list[bytes] = []
        response_bytes = 0
        for chunk in response.iter_bytes():
            response_bytes += len(chunk)
            if response_bytes > MAX_RESPONSE_BYTES:
                raise SourceDataError("HiBob public feed exceeded its response byte limit")
            chunks.append(chunk)
        return FetchResult(payload=b"".join(chunks), etag=response.headers.get("etag"))


def scrape_postings(company: Company, payload: bytes) -> ScrapeResult:
    origin = board_url(company)
    try:
        feed = HiBobFeed.model_validate_json(payload, strict=True)
        documents: list[RawDocument] = []
        identifiers: set[str] = set()
        for record in feed.jobAdDetails:
            posting = HiBobPosting.model_validate(record)
            if posting.id in identifiers:
                raise SourceDataError("HiBob returned duplicate posting IDs")
            identifiers.add(posting.id)
            documents.append(
                job_document(
                    company,
                    record,
                    feed_url=feed_url(company),
                    external_id=posting.id,
                    application_url=f"{origin}/jobs/{posting.id}",
                    apply_url=f"{origin}/jobs/{posting.id}/apply",
                )
            )
    except ValidationError:
        raise SourceDataError(
            "HiBob returned malformed jobs, missing full descriptions, or a challenge response"
        ) from None
    return ScrapeResult(fetched=len(feed.jobAdDetails), documents=documents)


def create_source(company: Company) -> JobSource:
    board_url(company)
    return JobSource(
        name=company.source_name,
        fetch=partial(fetch_postings, company),
        scrape=partial(scrape_postings, company),
    )
