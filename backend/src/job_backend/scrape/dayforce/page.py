import re

from job_backend.scrape.dayforce.constants import (
    DESCRIPTION_SELECTORS,
    LOCATION_SELECTORS,
    POSTED_SELECTORS,
    REQUISITION_SELECTORS,
    TITLE_SELECTORS,
)
from job_backend.scrape.pipeline.heuristics.markup import PageMarkup
from job_backend.scrape.pipeline.heuristics.models import PageFacts


def extract_page(markup: PageMarkup, _source_url: str) -> PageFacts:
    requisition = markup.first_text(REQUISITION_SELECTORS)
    match = re.fullmatch(r"Req\s*#\s*(\S+)", requisition or "", re.IGNORECASE)
    posted = markup.first_text(POSTED_SELECTORS)
    return PageFacts(
        title=markup.first_text(TITLE_SELECTORS),
        locations=markup.texts(LOCATION_SELECTORS),
        source_job_id=match.group(1) if match else None,
        date_posted=re.sub(r"^Posted\s+", "", posted) if posted else None,
        description="\n\n".join(
            node.text for selector in DESCRIPTION_SELECTORS for node in markup.select(selector)
        )
        or None,
    )
