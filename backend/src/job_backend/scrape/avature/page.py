import re
from functools import cache
from urllib.parse import urlsplit

from job_backend.scrape.avature.avature import closest
from job_backend.scrape.avature.constants import (
    DETAIL_FIELD,
    DETAIL_FIELD_LABEL,
    DETAIL_FIELD_VALUE,
    DETAILS,
    LOCATION_LABEL,
    REQUISITION_LABEL,
    TITLE,
)
from job_backend.scrape.pipeline.heuristics.markup import PageMarkup
from job_backend.scrape.pipeline.heuristics.models import PageFacts


@cache
def page_hosts() -> frozenset[str]:
    from job_backend.scrape.companies.companies import COMPANIES

    return frozenset(
        urlsplit(company.careers_url).hostname or ""
        for company in COMPANIES.values()
        if company.job_board == "avature"
    )


def detail_fields(markup: PageMarkup) -> list[tuple[str, str]]:
    fields = {id(field) for field in markup.select(DETAIL_FIELD)}
    labels: dict[int, str] = {}
    for label in markup.select(DETAIL_FIELD_LABEL):
        field = closest(label, lambda parent: id(parent) in fields)
        if field is not None and label.text:
            labels.setdefault(id(field), label.text)
    found: dict[str, str] = {}
    for value in markup.select(DETAIL_FIELD_VALUE):
        field = closest(value, lambda parent: id(parent) in labels)
        if field is not None and value.text:
            found.setdefault(labels[id(field)].rstrip(":").strip(), value.text)
    return list(found.items())


def extract_page(markup: PageMarkup, source_url: str) -> PageFacts:
    if "/JobDetail/" not in urlsplit(source_url).path:
        return PageFacts()
    fields = detail_fields(markup)
    title = next(
        (
            content
            for element in markup.select(TITLE)
            if (content := (element.attributes.get("content") or "").strip())
        ),
        None,
    )
    sections = [text for article in markup.select(DETAILS) if (text := markup.paragraphs(article))]
    return PageFacts(
        title=title,
        locations=[
            value for label, value in fields if re.search(LOCATION_LABEL, label, re.IGNORECASE)
        ],
        source_job_id=next(
            (
                value
                for label, value in fields
                if re.search(REQUISITION_LABEL, label, re.IGNORECASE)
            ),
            None,
        ),
        description="\n\n".join(sections) or None,
    )
