import re
from collections.abc import Callable
from functools import partial
from urllib.parse import urlencode, urljoin, urlsplit

import httpx2
from pydantic import JsonValue, TypeAdapter

from job_backend.scrape.avature.constants import (
    ITEM_LOCATION,
    JOB_PATH_PATTERN,
    LIST_FIELD,
    LIST_FIELD_LABEL,
    LIST_FIELD_VALUE,
    LOCATION_LABEL,
    MAX_PAGES_PER_TERM,
    MAX_RESPONSE_BYTES,
    NEXT_PAGE,
    SEARCH_TERMS,
)
from job_backend.scrape.companies.models import Company
from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.pipeline.heuristics.markup import PageElement, PageMarkup
from job_backend.scrape.pipeline.heuristics.models import PageSelector
from job_backend.scrape.pipeline.models import (
    FetchFailure,
    FetchResult,
    JobLink,
    JobSource,
    ScrapeResult,
)
from job_backend.scrape.utils.constants import IMPORTER_USER_AGENT, REQUEST_TIMEOUT
from job_backend.scrape.utils.pacing import pace_request, track_response


def portal_url(company: Company) -> str:
    if company.job_board != "avature" or company.board_name is None:
        raise ValueError("An Avature company and board_name are required")
    return company.careers_url.rstrip("/")


def search_url(company: Company, term: str, offset: int = 0) -> str:
    return f"{portal_url(company)}/SearchJobs/?{urlencode({'search': term, 'jobOffset': offset})}"


def closest(element: PageElement, match: Callable[[PageElement], bool]) -> PageElement | None:
    parent = element.parent
    while parent is not None and not match(parent):
        parent = parent.parent
    return parent


def _is_item(element: PageElement) -> bool:
    classes = (element.attributes.get("class") or "").split()
    return element.tag in {"article", "li"} or "list__item" in classes


def _item_locations(markup: PageMarkup) -> dict[int, str]:
    locations: dict[int, str] = {}
    for span in markup.select(ITEM_LOCATION):
        item = closest(span, _is_item)
        if item is not None and span.text:
            locations.setdefault(id(item), span.text)
    fields = {id(field) for field in markup.select(LIST_FIELD)}
    labels: dict[int, str] = {}
    for label in markup.select(LIST_FIELD_LABEL):
        field = closest(label, lambda parent: id(parent) in fields)
        if field is not None:
            labels[id(field)] = label.text
    for value in markup.select(LIST_FIELD_VALUE):
        field = closest(value, lambda parent: id(parent) in labels)
        if field is None or not re.search(LOCATION_LABEL, labels[id(field)], re.IGNORECASE):
            continue
        item = closest(field, _is_item)
        if item is not None and value.text:
            locations.setdefault(id(item), value.text)
    return locations


def parse_search(html: str, page_url: str, company_name: str) -> tuple[list[JobLink], bool]:
    markup = PageMarkup(html)
    host = urlsplit(page_url).hostname
    locations = _item_locations(markup)
    postings: dict[str, tuple[str, str, PageElement]] = {}
    for anchor in markup.select(PageSelector(tag="a")):
        parts = urlsplit(urljoin(page_url, anchor.attributes.get("href") or ""))
        match = re.search(JOB_PATH_PATTERN, parts.path)
        if match is None or parts.hostname != host:
            continue
        identifier = match.group("id")
        path, title, first = postings.get(identifier, (parts.path, "", anchor))
        postings[identifier] = (path, title or anchor.text, first)
    links: list[JobLink] = []
    for identifier, (path, title, anchor) in postings.items():
        listing_data: dict[str, JsonValue] = {"company_name": company_name}
        if title:
            listing_data["title"] = title
        item = closest(anchor, _is_item)
        if item is not None and id(item) in locations:
            listing_data["location"] = locations[id(item)]
        links.append(
            JobLink(
                url=f"https://{host}{path}",
                listing_url=page_url,
                date_posted=None,
                external_id=identifier,
                listing_data=listing_data,
            )
        )
    return links, bool(markup.select(NEXT_PAGE))


def _read(client: httpx2.Client, url: str) -> str:
    response = client.get(url)
    response.raise_for_status()
    if response.status_code == 202 or not response.content.strip():
        raise SourceDataError("Avature portal answered with a bot challenge instead of results")
    if urlsplit(str(response.url)).hostname != urlsplit(url).hostname:
        raise SourceDataError("Avature search redirected away from the career portal")
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise SourceDataError("Avature search page exceeded its byte limit")
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
                    rows, more = parse_search(_read(client, url), url, company.name)
                except (httpx2.HTTPError, SourceDataError) as error:
                    if not links and not failures and term == SEARCH_TERMS[0] and offset == 0:
                        raise
                    failures.append(FetchFailure(error, url))
                    break
                added = [row for row in rows if (row.external_id or row.url) not in links]
                links.update(((row.external_id or row.url), row) for row in added)
                offset += len(rows)
                if not added or not more:
                    break
            else:
                failures.append(
                    FetchFailure(
                        SourceDataError(
                            f"Avature search for {term!r} reached its {MAX_PAGES_PER_TERM}-page "
                            "limit; the results are partial"
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
    portal_url(company)
    return JobSource(
        name=company.source_name,
        fetch=partial(fetch_postings, company),
        scrape=scrape_postings,
        require_recent_dates=False,
        links_are_apply_urls=False,
        page_renderer="http",
        complete_listing=True,
    )
