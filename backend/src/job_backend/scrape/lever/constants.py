from job_backend.scrape.pipeline.heuristics.models import PageSelector

PAGE_HOSTS = ("jobs.lever.co", "jobs.eu.lever.co")
TITLE_SELECTORS = (PageSelector(tag="h2", ancestor_class="posting-headline"),)
LOCATION_SELECTORS = (
    PageSelector(attribute="class", value="location", ancestor_class="posting-categories"),
)
APPLY_SELECTORS = (PageSelector(tag="a", attribute="class", value="postings-btn"),)
