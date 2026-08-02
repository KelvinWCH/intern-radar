import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx2
from pydantic import JsonValue, TypeAdapter, ValidationError

from job_backend.scrape.eightfold.constants import BOARD_DOMAINS as EIGHTFOLD_DOMAINS
from job_backend.scrape.eightfold.models import EightfoldDetail, EightfoldEnvelope
from job_backend.scrape.pipeline.models import JobPageSettings, RawDocument
from job_backend.scrape.smartrecruiters.constants import API_ROOT as SMARTRECRUITERS_API
from job_backend.scrape.smartrecruiters.models import SmartRecruitersPosting
from job_backend.scrape.utils.constants import (
    EIGHTFOLD_HOST_SUFFIX,
    GREENHOUSE_API_ROOT,
    GREENHOUSE_PAGES,
    SMARTRECRUITERS_HOSTS,
)
from job_backend.scrape.utils.job_page_http import HttpPageStatusError
from job_backend.scrape.utils.pacing import observe_response
from job_backend.scrape.utils.public_urls import require_public_url, resolve_host
from job_backend.scrape.utils.robots import (
    RobotsDisallowedError,
    RobotsUnreachableError,
    require_robots_allowed,
)
from job_backend.scrape.workday.constants import PUBLIC_HOST_PATTERN, SITE_PATTERN
from job_backend.scrape.workday.models import WorkdayPostingDetail

_RECORD = TypeAdapter(dict[str, JsonValue])


@dataclass(frozen=True)
class PostingApi:
    api_url: str
    page_url: str
    wrap: Callable[[dict[str, JsonValue]], dict[str, JsonValue] | None]
    gone_on_error_record: bool = False


def _text(value: JsonValue) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _envelope(record: dict[str, JsonValue], company: str | None) -> dict[str, JsonValue]:
    envelope: dict[str, JsonValue] = {"job": {"detail": record}}
    if company:
        envelope["company_name"] = company
    return envelope


def _workday(url: str) -> PostingApi | None:
    parts = urlsplit(url)
    host = parts.hostname or ""
    match = re.fullmatch(PUBLIC_HOST_PATTERN, host)
    if match is None or parts.scheme != "https" or parts.port not in {None, 443}:
        return None
    segments = parts.path.strip("/").split("/")
    if segments and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", segments[0]):
        segments = segments[1:]
    if (
        len(segments) < 3
        or segments[1] != "job"
        or not re.fullmatch(SITE_PATTERN, segments[0])
        or any(segment in {"", ".", ".."} for segment in segments)
    ):
        return None
    site, path = segments[0], "/".join(segments[2:])

    def wrap(record: dict[str, JsonValue]) -> dict[str, JsonValue] | None:
        try:
            WorkdayPostingDetail.model_validate(record)
        except ValidationError:
            return None
        organization = record.get("hiringOrganization")
        company = _text(organization.get("name")) if isinstance(organization, dict) else None
        return _envelope(record, company)

    return PostingApi(
        api_url=f"https://{host}/wday/cxs/{match.group('tenant')}/{site}/job/{path}",
        page_url=f"https://{host}/{site}/job/{path}",
        wrap=wrap,
        gone_on_error_record=True,
    )


def _smartrecruiters(url: str) -> PostingApi | None:
    parts = urlsplit(url)
    if parts.hostname not in SMARTRECRUITERS_HOSTS or parts.scheme != "https":
        return None
    match = re.fullmatch(r"/([A-Za-z0-9_.-]+)/(\d+)(?:-[^/]*)?/?", parts.path)
    if match is None:
        return None
    company, identifier = match.groups()

    def wrap(record: dict[str, JsonValue]) -> dict[str, JsonValue] | None:
        try:
            posting = SmartRecruitersPosting.model_validate(record)
        except ValidationError:
            return None
        if posting.id != identifier:
            return None
        employer = record.get("company")
        name = _text(employer.get("name")) if isinstance(employer, dict) else None
        return _envelope(record, name)

    return PostingApi(
        api_url=f"{SMARTRECRUITERS_API}/{company}/postings/{identifier}",
        page_url=f"https://{parts.hostname}/{company}/{identifier}",
        wrap=wrap,
    )


def _eightfold(url: str) -> PostingApi | None:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.scheme != "https":
        return None
    if host in EIGHTFOLD_DOMAINS:
        domain = EIGHTFOLD_DOMAINS[host]
    elif host.endswith(EIGHTFOLD_HOST_SUFFIX) and host.count(".") == 2:
        domain = host.removesuffix(EIGHTFOLD_HOST_SUFFIX) + ".com"
    else:
        return None
    match = re.fullmatch(r"/careers/job/(\d+)/?", parts.path)
    pid = parse_qs(parts.query).get("pid", [])
    if match is None and not (parts.path.rstrip("/") == "/careers" and len(pid) == 1):
        return None
    identifier = int(match.group(1) if match is not None else pid[0])

    def wrap(record: dict[str, JsonValue]) -> dict[str, JsonValue] | None:
        try:
            detail = EightfoldDetail.model_validate(EightfoldEnvelope.model_validate(record).data)
        except ValidationError:
            return None
        return _envelope(record, None) if detail.id == identifier else None

    query = urlencode({"position_id": identifier, "domain": domain, "hl": "en"})
    return PostingApi(
        api_url=f"https://{host}/api/pcsx/position_details?{query}",
        page_url=f"https://{host}/careers/job/{identifier}",
        wrap=wrap,
    )


def _greenhouse(url: str) -> PostingApi | None:
    parts = urlsplit(url)
    page = GREENHOUSE_PAGES.get(parts.hostname or "")
    if page is None or parts.scheme != "https":
        return None
    board, company, pattern = page
    match = re.fullmatch(pattern, parts.path)
    if match is None:
        return None
    identifier = match.group("id")

    def wrap(record: dict[str, JsonValue]) -> dict[str, JsonValue] | None:
        if str(record.get("id")) != identifier or not _text(record.get("title")):
            return None
        return {"company_name": company, "job": record}

    return PostingApi(
        api_url=f"{GREENHOUSE_API_ROOT}/{board}/jobs/{identifier}",
        page_url=f"https://{parts.hostname}{parts.path}",
        wrap=wrap,
    )


def posting_api(url: str) -> PostingApi | None:
    for locate in (_workday, _smartrecruiters, _eightfold, _greenhouse):
        found = locate(url)
        if found is not None:
            return found
    return None


def read_posting_api(
    url: str,
    *,
    client: httpx2.Client,
    settings: JobPageSettings,
    resolver: Callable[[str], tuple[str, ...]] = resolve_host,
) -> RawDocument | None:
    api = posting_api(url)
    if api is None:
        return None
    require_public_url(api.api_url, resolver=resolver)
    # this reads a job link through an endpoint instead of the page, so the endpoint's
    # robots.txt applies too; when it says no, the page is read and gets its own check
    try:
        require_robots_allowed(api.api_url)
    except (RobotsDisallowedError, RobotsUnreachableError):
        return None
    try:
        with client.stream("GET", api.api_url) as response:
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > settings.max_page_bytes:
                    return None
                chunks.append(chunk)
            status = response.status_code
            retry_after = response.headers.get("retry-after")
    except httpx2.HTTPError:
        return None
    try:
        record: dict[str, JsonValue] | None = _RECORD.validate_json(b"".join(chunks))
    except ValidationError:
        record = None
    if status in {404, 410} or (
        status == 403 and api.gone_on_error_record and record is not None and "errorCode" in record
    ):
        raise HttpPageStatusError(404)
    observe_response(api.api_url, status, retry_after)
    if status != 200 or record is None:
        return None
    envelope = api.wrap(record)
    if envelope is None:
        return None
    return RawDocument(
        content=json.dumps(envelope, ensure_ascii=False, sort_keys=True),
        source_url=api.api_url,
        media_type="application/json",
        application_url=api.page_url,
    )
