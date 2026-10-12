import re

from job_backend.scrape.pipeline.heuristics.markup import PageMarkup
from job_backend.scrape.pipeline.heuristics.models import PageFacts
from job_backend.scrape.workday.constants import (
    APPLY_SELECTORS,
    DATE_SELECTORS,
    IDENTIFIER_SELECTORS,
    LOCATION_SELECTORS,
    TITLE_SELECTORS,
)


def extract_page(markup: PageMarkup, source_url: str) -> PageFacts:
    identifier = markup.first_text(IDENTIFIER_SELECTORS)
    posted = markup.first_text(DATE_SELECTORS)
    return PageFacts(
        title=markup.first_text(TITLE_SELECTORS),
        locations=[
            re.sub(r"^locations?\s*:?\s*", "", value, flags=re.IGNORECASE)
            for value in markup.texts(LOCATION_SELECTORS)
        ],
        source_job_id=re.sub(
            r"^(?:job\s+)?requisition\s+id\s*:?\s*", "", identifier, flags=re.IGNORECASE
        )
        if identifier
        else None,
        date_posted=re.sub(r"^posted\s+(?:on\s+)?", "", posted, flags=re.IGNORECASE)
        if posted
        else None,
        apply_url=markup.link(APPLY_SELECTORS, source_url),
    )
