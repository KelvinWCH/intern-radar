from datetime import datetime
from functools import cache

from job_backend.scrape.pipeline.heuristics.markup import PageMarkup
from job_backend.scrape.pipeline.heuristics.models import PageFacts, PageSelector
from job_backend.scrape.successfactors.constants import (
    DESCRIPTION_SELECTORS,
    LOCATION_SELECTORS,
    POSTED_FORMAT,
    TITLE_SELECTORS,
)


@cache
def page_hosts() -> frozenset[str]:
    from job_backend.scrape.companies.companies import COMPANIES

    return frozenset(
        company.board_name
        for company in COMPANIES.values()
        if company.job_board == "successfactors" and company.board_name
    )


def _meta(markup: PageMarkup, attribute: str, name: str) -> str | None:
    for element in markup.select(PageSelector(tag="meta", attribute=attribute, value=name)):
        content = (element.attributes.get("content") or "").strip()
        if content:
            return content
    return None


def posted_date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return datetime.strptime(value, POSTED_FORMAT).date().isoformat()
    except ValueError:
        return None


def extract_page(markup: PageMarkup, _source_url: str) -> PageFacts:
    description = next(
        (
            text
            for selector in DESCRIPTION_SELECTORS
            for element in markup.select(selector)[:1]
            if (text := markup.paragraphs(element))
        ),
        None,
    )
    address = _meta(markup, "itemprop", "streetAddress")
    return PageFacts(
        title=markup.first_text(TITLE_SELECTORS) or _meta(markup, "property", "og:title"),
        locations=markup.texts(LOCATION_SELECTORS) or ([address] if address else []),
        date_posted=posted_date(_meta(markup, "itemprop", "datePosted")),
        description=description,
    )
