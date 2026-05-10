import re

from job_backend.scrape.greenhouse.constants import (
    APPLY_SELECTORS,
    COMPANY_SELECTORS,
    LOCATION_SELECTORS,
    TITLE_SELECTORS,
)
from job_backend.scrape.pipeline.heuristics.markup import PageMarkup
from job_backend.scrape.pipeline.heuristics.models import PageFacts


def extract_page(markup: PageMarkup, source_url: str) -> PageFacts:
    company = markup.first_text(COMPANY_SELECTORS)
    return PageFacts(
        title=markup.first_text(TITLE_SELECTORS),
        company_name=re.sub(r"^at\s+", "", company, flags=re.IGNORECASE) if company else None,
        locations=markup.texts(LOCATION_SELECTORS),
        apply_url=markup.link(APPLY_SELECTORS, source_url),
    )
