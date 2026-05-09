import re
from functools import partial
from urllib.parse import urlencode, urljoin, urlsplit

import httpx2
from pydantic import JsonValue, TypeAdapter

from job_backend.scrape.companies.models import Company
from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.pipeline.heuristics.markup import PageElement, PageMarkup
from job_backend.scrape.pipeline.models import (
    FetchFailure,
    FetchResult,
    JobLink,
    JobSource,
    ScrapeResult,
)
from job_backend.scrape.successfactors.constants import (
    JOB_PATH_PATTERN,
    MAX_PAGES_PER_TERM,
    MAX_RESPONSE_BYTES,
    PAGE_SIZE,
    RESULT_COUNT,
    ROW_LINK,
    ROW_LOCATION,
    SEARCH_FORM,
    SEARCH_PATH,
    SEARCH_TERMS,
)
from job_backend.scrape.utils.constants import IMPORTER_USER_AGENT, REQUEST_TIMEOUT
from job_backend.scrape.utils.pacing import pace_request, track_response


def board_host(company: Company) -> str:
    if company.job_board != "successfactors" or company.board_name is None:
        raise ValueError("A SuccessFactors company and board_name are required")
    return company.board_name


def search_url(company: Company, term: str, offset: int = 0) -> str:
    query = urlencode({"q": term, "startrow": offset})
    return f"https://{board_host(company)}{SEARCH_PATH}?{query}"


def _ancestor(element: PageElement, tag: str) -> PageElement | None:
    parent = element.parent
    while parent is not None and parent.tag != tag:
        parent = parent.parent
    return parent


def parse_search(html: str, page_url: str, company_name: str) -> tuple[list[JobLink], int]:
    markup = PageMarkup(html)
    host = urlsplit(page_url).hostname
    locations: dict[int, str] = {}
    for span in markup.select(ROW_LOCATION):
        row = _ancestor(span, "tr")
        if row is not None and span.text and id(row) not in locations:
            locations[id(row)] = span.text
    links: dict[str, JobLink] = {}
    for anchor in markup.select(ROW_LINK):
        url = urljoin(page_url, anchor.attributes.get("href") or "")
        parts = urlsplit(url)
        match = re.fullmatch(JOB_PATH_PATTERN, parts.path)
        if match is None or parts.hostname != host or not anchor.text:
            continue
        identifier = match.group("id")
        if identifier in links:
            continue
        row = _ancestor(anchor, "tr")
        listing_data: dict[str, JsonValue] = {"title": anchor.text, "company_name": company_name}
        if row is not None and id(row) in locations:
            listing_data["location"] = locations[id(row)]
        links[identifier] = JobLink(
            url=f"https://{host}{parts.path}",
            listing_url=page_url,
            date_posted=None,
            external_id=identifier,
            listing_data=listing_data,
        )
    total = 0
    for label in markup.select(RESULT_COUNT):
        numbers = re.findall(r"\d[\d,]*", label.text)
        if numbers:
            total = int(numbers[-1].replace(",", ""))
            break
    if not links and not total and not markup.select(SEARCH_FORM):
        raise SourceDataError("SuccessFactors returned an unrecognized search page")
    return list(links.values()), total


def _read(client: httpx2.Client, url: str) -> str:
    response = client.get(url)
    response.raise_for_status()
    if urlsplit(str(response.url)).hostname != urlsplit(url).hostname:
        raise SourceDataError("SuccessFactors search redirected away from the career site")
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise SourceDataError("SuccessFactors search page exceeded its byte limit")
    return response.text


def fetch_postings(
    company: Company, _etag: str | None, *, transport: httpx2.BaseTransport | None = None
) -> FetchResult:
    links: dict[str, JobLink] = {}
    failures: list[FetchFailure] = []
    with httpx2.Client(
        event_hooks={"request": [pace_request], "response": [track_response]},
        transport=transport,
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": IMPORTER_USER_AGENT,
        },
    ) as client:
        for term in SEARCH_TERMS:
            offset = 0
            for _ in range(MAX_PAGES_PER_TERM):
                url = search_url(company, term, offset)
                try:
                    rows, total = parse_search(_read(client, url), url, company.name)
                except (httpx2.HTTPError, SourceDataError) as error:
                    if not links and not failures and term == SEARCH_TERMS[0] and offset == 0:
                        raise
                    failures.append(FetchFailure(error, url))
                    break
                # one link per posting id or the page reader rejects it
                added = [row for row in rows if (row.external_id or row.url) not in links]
                links.update(((row.external_id or row.url), row) for row in added)
                offset += PAGE_SIZE
                if not added or offset >= total:
                    break
            else:
                failures.append(
                    FetchFailure(
                        SourceDataError(
                            f"SuccessFactors search for {term!r} reached its "
                            f"{MAX_PAGES_PER_TERM}-page limit; the results are partial"
                        ),
                        search_url(company, term, offset),
                    )
                )
    return FetchResult(
        TypeAdapter(list[JobLink]).dump_json(list(links.values())), None, tuple(failures)
    )


def scrape_postings(payload: bytes) -> ScrapeResult:
    links = TypeAdapter(list[JobLink]).validate_json(payload, strict=True)
    return ScrapeResult(fetched=len(links), links=links)


def create_source(company: Company) -> JobSource:
    board_host(company)
    return JobSource(
        name=company.source_name,
        fetch=partial(fetch_postings, company),
        scrape=scrape_postings,
        require_recent_dates=False,
        links_are_apply_urls=False,
        page_renderer="http",
        complete_listing=True,
    )
