import hashlib
import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from functools import partial
from urllib.parse import urlsplit

import httpx2
from pydantic import JsonValue, TypeAdapter, ValidationError

from job_backend.scrape.companies.documents import job_document
from job_backend.scrape.companies.models import Company
from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.pipeline.heuristics.classification import classify_locations
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
from job_backend.scrape.workday.constants import (
    COUNTRY_FACETS,
    DETAIL_BATCH_DELAY_SECONDS,
    DETAIL_WORKERS,
    LISTING_RESULT_CAP,
    LOCATION_FACETS,
    LOCATION_FILTER_MIN_TOTAL,
    MAINTENANCE_HOST,
    MAX_LISTING_PAGES,
    MAX_REQUEST_ATTEMPTS,
    MAX_RESPONSE_BYTES,
    MAX_RETRY_DELAY_SECONDS,
    MAX_SNAPSHOT_BYTES,
    PAGE_SIZE,
    PARTITION_FACETS,
    PROVINCE_CODES,
    PUBLIC_HOST_PATTERN,
    RETRY_BASE_SECONDS,
    RETRYABLE_STATUS_CODES,
    SITE_PATTERN,
    STUDENT_FACET_VALUE,
)
from job_backend.scrape.workday.models import (
    WorkdayBoard,
    WorkdayFacet,
    WorkdayListing,
    WorkdayListingBudget,
    WorkdayListingPage,
    WorkdayPostingDetail,
    WorkdayRecord,
)


def board_coordinates(company: Company) -> WorkdayBoard:
    parsed = urlsplit(company.careers_url)
    match = re.fullmatch(PUBLIC_HOST_PATTERN, parsed.hostname or "")
    site = company.board_name
    if (
        company.job_board != "workday"
        or site is None
        or not re.fullmatch(SITE_PATTERN, site)
        or match is None
        or parsed.scheme != "https"
        or parsed.port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("Workday requires a public HTTPS myworkdayjobs.com board and site name")
    segments = parsed.path.strip("/").split("/")
    if segments not in ([site], ["en-US", site]) and not (
        len(segments) == 2
        and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", segments[0])
        and segments[1] == site
    ):
        raise ValueError("Workday careers_url must identify its configured public site")
    origin = f"https://{parsed.hostname}"
    return WorkdayBoard(
        api_url=f"{origin}/wday/cxs/{match.group('tenant')}/{site}",
        careers_url=f"{origin}/{site}",
    )


def feed_url(company: Company) -> str:
    return f"{board_coordinates(company).api_url}/jobs"


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


def _request_record_once(
    client: httpx2.Client, url: str, body: dict[str, JsonValue] | None = None
) -> dict[str, JsonValue]:
    method = "POST" if body is not None else "GET"
    with client.stream(method, url, json=body) as response:
        if (
            response.is_redirect
            and urlsplit(response.headers.get("location", "")).hostname == MAINTENANCE_HOST
        ):
            raise SourceDataError(
                "Workday is down for its scheduled maintenance; the board is read again "
                "on the next run"
            )
        response.raise_for_status()
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise SourceDataError("Workday response exceeded its byte limit")
            chunks.append(chunk)
    try:
        return TypeAdapter(dict[str, JsonValue]).validate_json(b"".join(chunks), strict=True)
    except ValidationError:
        raise SourceDataError("Workday returned malformed JSON or a challenge page") from None


def _request_record(
    client: httpx2.Client, url: str, body: dict[str, JsonValue] | None = None
) -> dict[str, JsonValue]:
    for attempt in range(MAX_REQUEST_ATTEMPTS):
        try:
            return _request_record_once(client, url, body)
        except httpx2.HTTPStatusError as error:
            if (
                error.response.status_code not in RETRYABLE_STATUS_CODES
                or attempt == MAX_REQUEST_ATTEMPTS - 1
            ):
                raise
            delay = _retry_delay(error.response, attempt)
            if delay > MAX_RETRY_DELAY_SECONDS:
                # never retry before the servers retry-after time
                raise
            time.sleep(delay)
        except httpx2.TransportError:
            if attempt == MAX_REQUEST_ATTEMPTS - 1:
                raise
            time.sleep(_retry_delay(None, attempt))
    raise SourceDataError("Workday request attempts were exhausted")


def _partitioned_records(
    client: httpx2.Client,
    board: WorkdayBoard,
    response: dict[str, JsonValue],
    budget: WorkdayListingBudget,
    applied_facets: dict[str, JsonValue],
) -> list[dict[str, JsonValue]]:
    facets = response.get("facets")
    if isinstance(facets, list):
        for parameter in PARTITION_FACETS:
            if parameter in applied_facets:
                continue
            for raw_facet in facets:
                if not isinstance(raw_facet, dict) or raw_facet.get("facetParameter") != parameter:
                    continue
                facet = WorkdayFacet.model_validate(raw_facet)
                if (
                    not facet.values
                    or any(value.count >= LISTING_RESULT_CAP for value in facet.values)
                    or sum(value.count for value in facet.values) < LISTING_RESULT_CAP
                ):
                    continue
                records: dict[str, dict[str, JsonValue]] = {}
                for value in facet.values:
                    if value.count == 0:
                        continue
                    partition = _listing_records(
                        client, board, {**applied_facets, parameter: [value.id]}, budget
                    )
                    if len(partition) < value.count:
                        raise SourceDataError("Workday partition ended before its facet count")
                    for record in partition:
                        records[WorkdayListing.model_validate(record).externalPath] = record
                if len(records) < sum(value.count for value in facet.values):
                    raise SourceDataError(
                        "Workday category partitions did not cover the reported total"
                    )
                if (
                    len(json.dumps(list(records.values()), ensure_ascii=False).encode())
                    > MAX_SNAPSHOT_BYTES
                ):
                    raise SourceDataError(
                        "Workday partitioned listings exceeded the snapshot byte limit"
                    )
                return list(records.values())
    raise SourceDataError(
        "Workday reached its result cap without complete usable category partitions"
    )


def _canada_facets(facets: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(facets, list):
        return {}
    for facet in facets:
        if not isinstance(facet, dict):
            continue
        parameter = facet.get("facetParameter")
        values = facet.get("values")
        if isinstance(parameter, str) and parameter.casefold() in COUNTRY_FACETS:
            identifiers: list[JsonValue] = (
                [
                    identifier
                    for value in values
                    if isinstance(value, dict)
                    and value.get("descriptor") == "Canada"
                    and isinstance(identifier := value.get("id"), str)
                    and identifier
                ]
                if isinstance(values, list)
                else []
            )
            if identifiers:
                return {parameter: identifiers}
        nested = _canada_facets(values)
        if nested:
            return nested
    return {}


def canadian_place(descriptor: str) -> bool:
    if re.match(r"(?:CA|CAN)-", descriptor):
        return True
    if re.match(r"[A-Z]{2,3}-[A-Z0-9]{1,3}-", descriptor):
        return False
    if re.search(rf"\b(?:Canada|CAN)\b|\b{PROVINCE_CODES}\s+CA\b", descriptor):
        return True
    parts = [part.strip() for part in descriptor.split(",") if part.strip()]
    if len(parts) > 1:
        return bool(re.fullmatch(PROVINCE_CODES, parts[-1]) or classify_locations([parts[-1]])[0])
    return classify_locations([descriptor])[0]


def canadian_locations(facets: JsonValue, total: int) -> dict[str, JsonValue]:
    if not isinstance(facets, list):
        return {}
    for facet in facets:
        if not isinstance(facet, dict):
            continue
        parameter = facet.get("facetParameter")
        values = facet.get("values")
        if (
            isinstance(parameter, str)
            and parameter.casefold() in LOCATION_FACETS
            and isinstance(values, list)
        ):
            selected = [
                value
                for value in values
                if isinstance(value, dict)
                and isinstance(descriptor := value.get("descriptor"), str)
                and canadian_place(descriptor)
                and isinstance(value.get("id"), str)
                and value.get("id")
            ]
            postings = sum(
                count for value in selected if isinstance(count := value.get("count"), int)
            )
            if selected and postings * 2 < total:
                return {parameter: [value["id"] for value in selected]}
            if selected:
                return {}
        nested = canadian_locations(values, total)
        if nested:
            return nested
    return {}


def student_facets(facets: JsonValue) -> dict[str, list[tuple[str, str]]]:
    found: dict[str, list[tuple[str, str]]] = {}
    if not isinstance(facets, list):
        return found
    for facet in facets:
        if not isinstance(facet, dict):
            continue
        parameter = facet.get("facetParameter")
        values = facet.get("values")
        if not isinstance(values, list):
            continue
        if isinstance(parameter, str) and parameter.casefold() not in (
            COUNTRY_FACETS | LOCATION_FACETS
        ):
            matches = [
                (identifier, descriptor)
                for value in values
                if isinstance(value, dict)
                and isinstance(identifier := value.get("id"), str)
                and identifier
                and isinstance(descriptor := value.get("descriptor"), str)
                and re.search(STUDENT_FACET_VALUE, descriptor, re.IGNORECASE)
            ]
            if matches:
                found[parameter] = matches
        for parameter, matches in student_facets(values).items():
            found.setdefault(parameter, matches)
    return found


def _student_paths(
    client: httpx2.Client, board: WorkdayBoard, budget: WorkdayListingBudget
) -> dict[str, str]:
    paths: dict[str, str] = {}
    for parameter, values in student_facets(budget.facets).items():
        label = ", ".join(dict.fromkeys(descriptor for _identifier, descriptor in values))
        subset = _listing_records(
            client,
            board,
            {**budget.scope, parameter: [identifier for identifier, _descriptor in values]},
            WorkdayListingBudget(),
        )
        for record in subset:
            path = _listing_path(record)
            if path is not None:
                paths.setdefault(path, label)
    return paths


def _listing_path(record: dict[str, JsonValue]) -> str | None:
    try:
        return WorkdayListing.model_validate(record).externalPath
    except ValidationError:
        return None


def _listing_records(
    client: httpx2.Client,
    board: WorkdayBoard,
    applied_facets: dict[str, JsonValue] | None = None,
    budget: WorkdayListingBudget | None = None,
) -> list[dict[str, JsonValue]]:
    budget = budget or WorkdayListingBudget()
    filters = applied_facets or {}
    listings: list[dict[str, JsonValue]] = []
    seen_paths: set[str] = set()
    reported_total = 0
    offset = 0
    for _ in range(MAX_LISTING_PAGES):
        budget.pages += 1
        if budget.pages > MAX_LISTING_PAGES:
            raise SourceDataError("Workday exceeded the shared listing page limit")
        response = _request_record(
            client,
            f"{board.api_url}/jobs",
            {
                "appliedFacets": filters,
                "limit": PAGE_SIZE,
                "offset": offset,
                "searchText": "",
            },
        )
        page = WorkdayListingPage.model_validate(response)
        if not offset and not filters:
            canada = _canada_facets(response.get("facets")) or (
                canadian_locations(response.get("facets"), page.total)
                if page.total >= LOCATION_FILTER_MIN_TOTAL
                else {}
            )
            if canada:
                return _listing_records(client, board, canada, budget)
        if not offset and budget.facets is None:
            budget.facets = response.get("facets")
            budget.scope = dict(filters)
        if not offset and page.total >= LISTING_RESULT_CAP:
            return _partitioned_records(client, board, response, budget, filters)
        reported_total = max(reported_total, page.total)
        if not page.jobPostings:
            if len(listings) + budget.malformed + budget.repeated < reported_total:
                raise SourceDataError("Workday listing ended before its reported total")
            return listings
        added = repeated = 0
        for record in page.jobPostings:
            path = _listing_path(record)
            if path is None:
                # one broken listing shouldnt hide the rest
                budget.malformed += 1
                continue
            if path in seen_paths:
                repeated += 1
                continue
            seen_paths.add(path)
            budget.bytes += len(json.dumps(record, ensure_ascii=False).encode())
            if budget.bytes > MAX_SNAPSHOT_BYTES:
                raise SourceDataError("Workday listings exceeded the snapshot byte limit")
            listings.append(record)
            added += 1
        offset = len(listings) if added else offset + len(page.jobPostings)
        if not added and offset >= reported_total:
            budget.missing += max(
                0, reported_total - len(listings) - budget.malformed - budget.repeated
            )
            return listings
        budget.repeated += repeated
    raise SourceDataError("Workday exceeded the listing page limit before completion")


def _complete_record(
    client: httpx2.Client, board: WorkdayBoard, listing: dict[str, JsonValue]
) -> dict[str, JsonValue] | FetchFailure:
    url = f"{board.api_url}/jobs"
    try:
        posting = WorkdayListing.model_validate(listing)
        url = f"{board.api_url}{posting.externalPath}"
        detail = _request_record(client, url)
        WorkdayPostingDetail.model_validate(detail)
    except (httpx2.HTTPError, SourceDataError, ValidationError) as error:
        return FetchFailure(error, url)
    store_detail(url, detail)
    return {"listing": listing, "detail": detail}


def _cached_record(
    board: WorkdayBoard, listing: dict[str, JsonValue]
) -> dict[str, JsonValue] | None:
    path = _listing_path(listing)
    if path is None:
        return None
    detail = cached_detail(f"{board.api_url}{path}")
    if detail is None:
        return None
    try:
        WorkdayPostingDetail.model_validate(detail)
    except ValidationError:
        return None
    return {"listing": listing, "detail": detail}


def _with_student_facet(record: dict[str, JsonValue], label: str | None) -> dict[str, JsonValue]:
    return {**record, "student_facet": label} if label else record


def fetch_postings(
    company: Company, etag: str | None, *, transport: httpx2.BaseTransport | None = None
) -> FetchResult:
    board = board_coordinates(company)
    try:
        with httpx2.Client(
            event_hooks={"request": [pace_request], "response": [track_response]},
            transport=transport,
            timeout=REQUEST_TIMEOUT,
            headers={"Accept": "application/json", "User-Agent": IMPORTER_USER_AGENT},
        ) as client:
            budget = WorkdayListingBudget()
            listings = _listing_records(client, board, budget=budget)
            records: list[dict[str, JsonValue]] = []
            failures: list[FetchFailure] = []
            try:
                student_paths = _student_paths(client, board, budget)
            except (httpx2.HTTPError, SourceDataError, ValidationError) as error:
                student_paths = {}
                failures.append(FetchFailure(error, f"{board.api_url}/jobs"))
            if budget.malformed:
                failures.append(
                    FetchFailure(
                        SourceDataError(
                            f"Workday listed {budget.malformed} unreadable records; "
                            "the readable postings were imported"
                        ),
                        f"{board.api_url}/jobs",
                    )
                )
            if budget.missing:
                failures.append(
                    FetchFailure(
                        SourceDataError(
                            f"Workday stopped {budget.missing} postings short of its "
                            "advertised count; the postings read were imported"
                        ),
                        f"{board.api_url}/jobs",
                    )
                )
            snapshot_bytes = 0

            def keep(record: dict[str, JsonValue]) -> None:
                nonlocal snapshot_bytes
                snapshot_bytes += len(json.dumps(record, ensure_ascii=False).encode())
                if snapshot_bytes > MAX_SNAPSHOT_BYTES:
                    raise SourceDataError("Workday exceeded the snapshot byte limit")
                records.append(record)

            pending: list[dict[str, JsonValue]] = []
            for listing in listings:
                student = student_paths.get(_listing_path(listing) or "")
                if student is None and not listing_is_candidate(listing, complete=True):
                    keep({"listing": listing})
                    continue
                cached = _cached_record(board, listing)
                if cached is None:
                    pending.append(listing)
                else:
                    keep(_with_student_facet(cached, student))
            with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as executor:
                # small batches so pending responses stay bounded
                for start in range(0, len(pending), DETAIL_WORKERS):
                    if start and transport is None:
                        time.sleep(DETAIL_BATCH_DELAY_SECONDS)
                    batch = pending[start : start + DETAIL_WORKERS]
                    for record in executor.map(partial(_complete_record, client, board), batch):
                        if isinstance(record, FetchFailure):
                            failures.append(record)
                            continue
                        listing = record["listing"]
                        path = _listing_path(listing) if isinstance(listing, dict) else None
                        keep(_with_student_facet(record, student_paths.get(path or "")))
            records.sort(key=lambda record: json.dumps(record.get("listing"), sort_keys=True))
    except ValidationError:
        raise SourceDataError("Workday returned a malformed listing page") from None
    if failures and not records:
        raise SourceDataError("Workday returned malformed or unavailable complete posting records")
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True).encode()
    if len(payload) > MAX_SNAPSHOT_BYTES:
        raise SourceDataError("Workday exceeded the snapshot byte limit")
    snapshot_etag = None if failures else f"sha256:{hashlib.sha256(payload).hexdigest()}"
    return FetchResult(
        payload=None if snapshot_etag is not None and etag == snapshot_etag else payload,
        etag=snapshot_etag,
        failures=tuple(failures),
    )


def scrape_postings(company: Company, payload: bytes) -> ScrapeResult:
    board = board_coordinates(company)
    try:
        records = TypeAdapter(list[WorkdayRecord]).validate_json(payload, strict=True)
        documents: list[RawDocument] = []
        listed_urls: list[str] = []
        identifiers: set[str] = set()
        for record in records:
            try:
                listing = WorkdayListing.model_validate(record.listing)
                if record.detail is None:
                    listed_urls.append(f"{board.careers_url}{listing.externalPath}")
                    continue
                posting = WorkdayPostingDetail.model_validate(record.detail).jobPostingInfo
            except ValidationError:
                continue
            if posting.id in identifiers:
                continue
            identifiers.add(posting.id)
            original: dict[str, JsonValue] = {"listing": record.listing, "detail": record.detail}
            if record.student_facet:
                original["student_facet"] = record.student_facet
            documents.append(
                job_document(
                    company,
                    original,
                    feed_url=f"{board.api_url}{listing.externalPath}",
                    external_id=posting.id,
                    application_url=posting.externalUrl
                    or f"{board.careers_url}{listing.externalPath}",
                    apply_url=None,
                )
            )
    except ValidationError:
        raise SourceDataError("Workday returned a malformed snapshot") from None
    if records and not documents and not listed_urls:
        raise SourceDataError("Workday returned no readable complete posting records")
    return ScrapeResult(fetched=len(records), documents=documents, listed_urls=tuple(listed_urls))


def create_source(company: Company) -> JobSource:
    board_coordinates(company)
    return JobSource(
        name=company.source_name,
        fetch=partial(fetch_postings, company),
        scrape=partial(scrape_postings, company),
        complete_listing=True,
    )
