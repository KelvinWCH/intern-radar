import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import httpx2
from pydantic import JsonValue, TypeAdapter, ValidationError

from job_backend.scrape.companies.documents import job_document
from job_backend.scrape.companies.models import Company
from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.pipeline.heuristics.targeting import listing_is_candidate
from job_backend.scrape.pipeline.models import (
    FetchFailure,
    FetchResult,
    JobSource,
    RawDocument,
    ScrapeResult,
)
from job_backend.scrape.smartrecruiters.constants import (
    API_ROOT,
    COUNTRY,
    DETAIL_BATCH_DELAY_SECONDS,
    DETAIL_WORKERS,
    MAX_LISTING_PAGES,
    MAX_RESPONSE_BYTES,
    MAX_SNAPSHOT_BYTES,
    PAGE_SIZE,
    PUBLIC_POSTING_ROOT,
)
from job_backend.scrape.smartrecruiters.models import (
    SmartRecruitersListing,
    SmartRecruitersPage,
    SmartRecruitersPosting,
    SmartRecruitersRecord,
)
from job_backend.scrape.utils.constants import IMPORTER_USER_AGENT, REQUEST_TIMEOUT
from job_backend.scrape.utils.detail_cache import cached_detail, store_detail
from job_backend.scrape.utils.pacing import pace_request, track_response


def company_identifier(company: Company) -> str:
    if company.job_board != "smartrecruiters" or company.board_name is None:
        raise ValueError("A SmartRecruiters company and board_name are required")
    return company.board_name


def feed_url(company: Company) -> str:
    return f"{API_ROOT}/{company_identifier(company)}/postings?country={COUNTRY}"


def _get_json(client: httpx2.Client, url: str) -> dict[str, JsonValue]:
    response = client.get(url)
    response.raise_for_status()
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise SourceDataError("SmartRecruiters response exceeded its byte limit")
    try:
        return TypeAdapter(dict[str, JsonValue]).validate_json(response.content, strict=True)
    except ValidationError:
        raise SourceDataError("SmartRecruiters returned malformed JSON") from None


def _listings(client: httpx2.Client, company: Company) -> list[dict[str, JsonValue]]:
    listings: list[dict[str, JsonValue]] = []
    seen: set[str] = set()
    total = 0
    for page_number in range(MAX_LISTING_PAGES):
        url = f"{feed_url(company)}&limit={PAGE_SIZE}&offset={page_number * PAGE_SIZE}"
        try:
            page = SmartRecruitersPage.model_validate(_get_json(client, url))
        except ValidationError:
            raise SourceDataError("SmartRecruiters returned a malformed listing page") from None
        total = max(total, page.totalFound)
        if not page.content:
            return listings
        added = 0
        for record in page.content:
            try:
                listing = SmartRecruitersListing.model_validate(record)
            except ValidationError:
                continue
            if listing.id in seen:
                continue
            seen.add(listing.id)
            listings.append(record)
            added += 1
        if not added or len(listings) >= total:
            return listings
    raise SourceDataError("SmartRecruiters exceeded the listing page limit")


def _detail_url(company: Company, listing: dict[str, JsonValue]) -> str:
    identifier = SmartRecruitersListing.model_validate(listing).id
    return f"{API_ROOT}/{company_identifier(company)}/postings/{identifier}"


def _cached_record(company: Company, listing: dict[str, JsonValue]) -> dict[str, JsonValue] | None:
    try:
        detail = cached_detail(_detail_url(company, listing))
        if detail is None:
            return None
        SmartRecruitersPosting.model_validate(detail)
    except ValidationError:
        return None
    return {"listing": listing, "detail": detail}


def _complete_record(
    client: httpx2.Client, company: Company, listing: dict[str, JsonValue]
) -> dict[str, JsonValue] | FetchFailure:
    url = feed_url(company)
    try:
        url = _detail_url(company, listing)
        detail = _get_json(client, url)
        SmartRecruitersPosting.model_validate(detail)
    except (httpx2.HTTPError, SourceDataError, ValidationError) as error:
        return FetchFailure(error, url)
    store_detail(url, detail)
    return {"listing": listing, "detail": detail}


def fetch_postings(
    company: Company, etag: str | None, *, transport: httpx2.BaseTransport | None = None
) -> FetchResult:
    with httpx2.Client(
        event_hooks={"request": [pace_request], "response": [track_response]},
        transport=transport,
        timeout=REQUEST_TIMEOUT,
        headers={"Accept": "application/json", "User-Agent": IMPORTER_USER_AGENT},
    ) as client:
        listings = [record for record in _listings(client, company) if listing_is_candidate(record)]
        records: list[dict[str, JsonValue]] = []
        failures: list[FetchFailure] = []
        snapshot_bytes = 0

        def keep(record: dict[str, JsonValue]) -> None:
            nonlocal snapshot_bytes
            snapshot_bytes += len(json.dumps(record, ensure_ascii=False).encode())
            if snapshot_bytes > MAX_SNAPSHOT_BYTES:
                raise SourceDataError("SmartRecruiters exceeded the snapshot byte limit")
            records.append(record)

        pending: list[dict[str, JsonValue]] = []
        for listing in listings:
            cached = _cached_record(company, listing)
            if cached is None:
                pending.append(listing)
            else:
                keep(cached)
        with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as executor:
            for start in range(0, len(pending), DETAIL_WORKERS):
                if start and transport is None:
                    time.sleep(DETAIL_BATCH_DELAY_SECONDS)
                batch = pending[start : start + DETAIL_WORKERS]
                for record in executor.map(partial(_complete_record, client, company), batch):
                    if isinstance(record, FetchFailure):
                        failures.append(record)
                        continue
                    keep(record)
        records.sort(key=lambda record: json.dumps(record.get("listing"), sort_keys=True))
    if failures and not records:
        raise SourceDataError("SmartRecruiters returned no readable complete postings")
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True).encode()
    snapshot_etag = None if failures else f"sha256:{hashlib.sha256(payload).hexdigest()}"
    return FetchResult(
        payload=None if snapshot_etag is not None and etag == snapshot_etag else payload,
        etag=snapshot_etag,
        failures=tuple(failures),
    )


def scrape_postings(company: Company, payload: bytes) -> ScrapeResult:
    identifier = company_identifier(company)
    try:
        records = TypeAdapter(list[SmartRecruitersRecord]).validate_json(payload, strict=True)
    except ValidationError:
        raise SourceDataError("SmartRecruiters returned a malformed snapshot") from None
    documents: list[RawDocument] = []
    seen: set[str] = set()
    for record in records:
        try:
            posting = SmartRecruitersPosting.model_validate(record.detail)
        except ValidationError:
            continue
        if posting.id in seen:
            continue
        seen.add(posting.id)
        page_url = posting.postingUrl or f"{PUBLIC_POSTING_ROOT}/{identifier}/{posting.id}"
        documents.append(
            job_document(
                company,
                {"listing": record.listing, "detail": record.detail},
                feed_url=f"{API_ROOT}/{identifier}/postings/{posting.id}",
                external_id=posting.id,
                application_url=page_url,
                apply_url=posting.applyUrl,
            )
        )
    if records and not documents:
        raise SourceDataError("SmartRecruiters returned no readable complete postings")
    return ScrapeResult(fetched=len(records), documents=documents)


def create_source(company: Company) -> JobSource:
    feed_url(company)
    return JobSource(
        name=company.source_name,
        fetch=partial(fetch_postings, company),
        scrape=partial(scrape_postings, company),
        complete_listing=True,
    )
