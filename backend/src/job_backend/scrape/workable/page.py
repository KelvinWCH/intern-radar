from job_backend.scrape.pipeline.heuristics.markup import PageMarkup
from job_backend.scrape.pipeline.heuristics.models import PageFacts
from job_backend.scrape.workable.constants import (
    APPLY_SELECTORS,
    COMPANY_SELECTORS,
    LOCATION_SELECTORS,
    TITLE_SELECTORS,
)


def extract_page(markup: PageMarkup, source_url: str) -> PageFacts:
    return PageFacts(
        title=markup.first_text(TITLE_SELECTORS),
        company_name=markup.first_text(COMPANY_SELECTORS),
        locations=markup.texts(LOCATION_SELECTORS),
        apply_url=markup.link(APPLY_SELECTORS, source_url),
    )
