from job_backend.scrape.pipeline.heuristics.models import PageSelector

PAGE_HOSTS = (
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "boards.eu.greenhouse.io",
    "job-boards.eu.greenhouse.io",
)
TITLE_SELECTORS = (
    PageSelector(tag="h1", attribute="class", value="app-title"),
    PageSelector(tag="h1", ancestor_class="job__title"),
    PageSelector(tag="h1", attribute="class", value="section-header"),
)
COMPANY_SELECTORS = (PageSelector(attribute="class", value="company-name"),)
LOCATION_SELECTORS = (
    PageSelector(attribute="class", value="job__location"),
    PageSelector(attribute="class", value="location"),
)
APPLY_SELECTORS = (PageSelector(tag="a", attribute="id", value="apply_button"),)
