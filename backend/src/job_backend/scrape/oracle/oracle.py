import hashlib
import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from functools import partial
from urllib.parse import urlencode, urlsplit

import httpx2
from pydantic import JsonValue, TypeAdapter, ValidationError

from job_backend.scrape.companies.documents import job_document
from job_backend.scrape.companies.models import Company
from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.oracle.constants import (
    COUNTRY,
    DETAIL_BATCH_DELAY_SECONDS,
    DETAIL_PATH,
    DETAIL_WORKERS,
    HOST_PATTERN,
    MAX_LISTING_PAGES,
    MAX_REQUEST_ATTEMPTS,
    MAX_RESPONSE_BYTES,
    MAX_RETRY_DELAY_SECONDS,
    MAX_SNAPSHOT_BYTES,
    PAGE_SIZE,
    RETRY_BASE_SECONDS,
    RETRYABLE_STATUS_CODES,
    SEARCH_PATH,
    SITE_PATH_PATTERN,
)
from job_backend.scrape.oracle.models import (
    OracleDetail,
    OracleDetails,
    OracleListingBudget,
    OracleRecord,
    OracleRequisition,
    OracleSearch,
    OracleSearchPage,
    OracleSite,
)
from job_backend.scrape.pipeline.heuristics.targeting import listing_is_candidate
from job_backend.scrape.pipeline.models import (
    FetchFailure,
    FetchResult,
    JobSource,
    RawDocument,
    ScrapeResult,
)
from job_backend.scrape.utils.constants import IMPORTER_USER_AGENT, REQUEST_TIMEOUT
from job_backend.scrape.utils.detail_cache import cached_detail, store_detail
from job_backend.scrape.utils.pacing import pace_request, track_response

_RECORD = TypeAdapter(dict[str, JsonValue])


def site_coordinates(company: Company) -> OracleSite:
    parsed = urlsplit(company.careers_url)
    host = parsed.hostname or ""
    match = re.fullmatch(SITE_PATH_PATTERN, parsed.path)
    if (
        company.job_board != "oracle"
        or company.board_name is None
        or parsed.scheme != "https"
        or parsed.port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(HOST_PATTERN, host)
        or match is None
    ):
        raise ValueError("Oracle requires a public HTTPS candidate-experience site and number")
    return OracleSite(host=host, site=match.group(1), site_number=company.board_name)


def page_url(site: OracleSite, identifier: str) -> str:
    return f"https://{site.host}/hcmUI/CandidateExperience/en/sites/{site.site}/job/{identifier}"


def detail_url(site: OracleSite, identifier: str) -> str:
    query = urlencode(
        {
            "onlyData": "true",
            "expand": "all",
            "finder": f'ById;Id="{identifier}",siteNumber={site.site_number}',
        }
    )
    return f"https://{site.host}{DETAIL_PATH}?{query}"


def _search_url(site: OracleSite, arguments: str) -> str:
    query = urlencode(
        {
            "onlyData": "true",
            "expand": "requisitionList.secondaryLocations",
            "finder": f"findReqs;siteNumber={site.site_number},{arguments}",
        }
    )
    return f"https://{site.host}{SEARCH_PATH}?{query}"


def _retry_delay(response: httpx2.Response | None, attempt: int) -> float:
    delay = RETRY_BASE_SECONDS * 2**attempt
    header = response.headers.get("Retry-After") if response is not None else None
    if header:
        try:
            advertised = float(header)
        except ValueError:
            try:
                deadline = parsedate_to_datetime(header)
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=UTC)
                advertised = (deadline - datetime.now(UTC)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                advertised = delay
        if math.isfinite(advertised):
            delay = max(delay, advertised)
    return delay


def _request_once(client: httpx2.Client, url: str) -> dict[str, JsonValue]:
    with client.stream("GET", url) as response:
        response.raise_for_status()
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise SourceDataError("Oracle response exceeded its byte limit")
            chunks.append(chunk)
    try:
        return _RECORD.validate_json(b"".join(chunks), strict=True)
    except ValidationError:
        raise SourceDataError("Oracle returned malformed JSON or a challenge page") from None


def _request(client: httpx2.Client, url: str) -> dict[str, JsonValue]:
    for attempt in range(MAX_REQUEST_ATTEMPTS):
        try:
            return _request_once(client, url)
        except httpx2.HTTPStatusError as error:
            if (
                error.response.status_code not in RETRYABLE_STATUS_CODES
                or attempt == MAX_REQUEST_ATTEMPTS - 1
            ):
                raise
            delay = _retry_delay(error.response, attempt)
            if delay > MAX_RETRY_DELAY_SECONDS:
                raise
            time.sleep(delay)
        except httpx2.TransportError:
            if attempt == MAX_REQUEST_ATTEMPTS - 1:
                raise
            time.sleep(_retry_delay(None, attempt))
    raise SourceDataError("Oracle request attempts were exhausted")


def _search(client: httpx2.Client, site: OracleSite, arguments: str) -> OracleSearchPage:
    try:
        return OracleSearch.model_validate(_request(client, _search_url(site, arguments))).items[0]
    except ValidationError:
        raise SourceDataError("Oracle returned a malformed search response") from None


def _country_location(client: httpx2.Client, site: OracleSite) -> int | None:
    page = _search(
        client,
        site,
        "facetsList=LOCATIONS,limit=1,offset=0,userTargetFacetName=LOCATIONS,"
        f'userTargetFacetInputTerm="{COUNTRY}"',
    )
    return next(
        (facet.Id for facet in page.locationsFacet if facet.Name == COUNTRY and facet.Id),
        None,
    )


def _listings(
    client: httpx2.Client, site: OracleSite, location: int, budget: OracleListingBudget
) -> list[dict[str, JsonValue]]:
    listings: list[dict[str, JsonValue]] = []
    seen: set[str] = set()
    total = 0
    offset = 0
    for _ in range(MAX_LISTING_PAGES):
        page = _search(
            client,
            site,
            f"facetsList=NONE,limit={PAGE_SIZE},offset={offset},sortBy=POSTING_DATES_DESC,"
            f"locationId={location}",
        )
        total = max(total, page.TotalJobsCount)
        if not page.requisitionList:
            return listings
        for record in page.requisitionList:
            try:
                identifier = OracleRequisition.model_validate(record).Id
            except ValidationError:
                budget.malformed += 1
                continue
            if identifier in seen:
                continue
            seen.add(identifier)
            listings.append(record)
        offset += len(page.requisitionList)
        if offset >= total:
            return listings
    raise SourceDataError("Oracle exceeded the listing page limit before completion")


def listing_view(record: dict[str, JsonValue]) -> dict[str, JsonValue]:
    places: list[JsonValue] = []
    primary = record.get("PrimaryLocation")
    if isinstance(primary, str) and primary.strip():
        places.append(primary)
    secondary = record.get("secondaryLocations")
    if isinstance(secondary, list):
        places.extend(
            name
            for item in secondary
            if isinstance(item, dict) and isinstance(name := item.get("Name"), str) and name
        )
    return {"title": record.get("Title"), "locations": places}


def _cached_record(site: OracleSite, listing: dict[str, JsonValue]) -> dict[str, JsonValue] | None:
    identifier = OracleRequisition.model_validate(listing).Id
    detail = cached_detail(detail_url(site, identifier))
    if detail is None:
        return None
    try:
        OracleDetail.model_validate(detail)
    except ValidationError:
        return None
    return {"listing": listing, "detail": detail}


def _complete_record(
    client: httpx2.Client, site: OracleSite, listing: dict[str, JsonValue]
) -> dict[str, JsonValue] | FetchFailure:
    identifier = OracleRequisition.model_validate(listing).Id
    url = detail_url(site, identifier)
    try:
        details = OracleDetails.model_validate(_request(client, url))
        if not details.items:
            raise SourceDataError("Oracle no longer publishes this posting")
        detail = details.items[0]
        posting = OracleDetail.model_validate(detail)
        if posting.Id != identifier or not posting.has_description():
            raise SourceDataError("Oracle returned a different posting or no description")
    except (httpx2.HTTPError, SourceDataError, ValidationError) as error:
        return FetchFailure(error, url)
    store_detail(url, detail)
    return {"listing": listing, "detail": detail}


def fetch_postings(
    company: Company, etag: str | None, *, transport: httpx2.BaseTransport | None = None
) -> FetchResult:
    site = site_coordinates(company)
    budget = OracleListingBudget()
    records: list[dict[str, JsonValue]] = []
    failures: list[FetchFailure] = []
    snapshot_bytes = 0

    def keep(record: dict[str, JsonValue]) -> None:
        nonlocal snapshot_bytes
        snapshot_bytes += len(json.dumps(record, ensure_ascii=False).encode())
        if snapshot_bytes > MAX_SNAPSHOT_BYTES:
            raise SourceDataError("Oracle exceeded the snapshot byte limit")
        records.append(record)

    with httpx2.Client(
        event_hooks={"request": [pace_request], "response": [track_response]},
        transport=transport,
        timeout=REQUEST_TIMEOUT,
        headers={
            "Accept": "application/json",
            "Accept-Language": "en",
            "User-Agent": IMPORTER_USER_AGENT,
        },
    ) as client:
        location = _country_location(client, site)
        listings = _listings(client, site, location, budget) if location is not None else []
        if budget.malformed:
            failures.append(
                FetchFailure(
                    SourceDataError(
                        f"Oracle listed {budget.malformed} unreadable records; "
                        "the readable postings were imported"
                    ),
                    f"https://{site.host}{SEARCH_PATH}",
                )
            )
        pending: list[dict[str, JsonValue]] = []
        for listing in listings:
            if not listing_is_candidate(listing_view(listing)):
                keep({"listing": listing})
                continue
            cached = _cached_record(site, listing)
            if cached is None:
                pending.append(listing)
            else:
                keep(cached)
        with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as executor:
            for start in range(0, len(pending), DETAIL_WORKERS):
                if start and transport is None:
                    time.sleep(DETAIL_BATCH_DELAY_SECONDS)
                batch = pending[start : start + DETAIL_WORKERS]
                for record in executor.map(partial(_complete_record, client, site), batch):
                    if isinstance(record, FetchFailure):
                        failures.append(record)
                        continue
                    keep(record)
    records.sort(key=lambda record: json.dumps(record.get("listing"), sort_keys=True))
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True).encode()
    snapshot_etag = None if failures else f"sha256:{hashlib.sha256(payload).hexdigest()}"
    return FetchResult(
        payload=None if snapshot_etag is not None and etag == snapshot_etag else payload,
        etag=snapshot_etag,
        failures=tuple(failures),
    )


def scrape_postings(company: Company, payload: bytes) -> ScrapeResult:
    site = site_coordinates(company)
    try:
        records = TypeAdapter(list[OracleRecord]).validate_json(payload, strict=True)
    except ValidationError:
        raise SourceDataError("Oracle returned a malformed snapshot") from None
    documents: list[RawDocument] = []
    listed_urls: list[str] = []
    for record in records:
        try:
            identifier = OracleRequisition.model_validate(record.listing).Id
            if record.detail is None:
                listed_urls.append(page_url(site, identifier))
                continue
            OracleDetail.model_validate(record.detail)
        except ValidationError:
            continue
        documents.append(
            job_document(
                company,
                {"listing": record.listing, "detail": record.detail},
                feed_url=detail_url(site, identifier),
                external_id=identifier,
                application_url=page_url(site, identifier),
                apply_url=None,
            )
        )
    if records and not documents and not listed_urls:
        raise SourceDataError("Oracle returned no readable postings")
    return ScrapeResult(fetched=len(records), documents=documents, listed_urls=tuple(listed_urls))


def create_source(company: Company) -> JobSource:
    site_coordinates(company)
    return JobSource(
        name=company.source_name,
        fetch=partial(fetch_postings, company),
        scrape=partial(scrape_postings, company),
        complete_listing=True,
    )
