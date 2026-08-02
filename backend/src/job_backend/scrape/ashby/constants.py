from job_backend.scrape.pipeline.heuristics.models import PageSelector

PAGE_HOSTS = ("jobs.ashbyhq.com",)
TITLE_SELECTORS = (
    PageSelector(tag="h1", ancestor_class="ashby-job-posting-heading"),
    PageSelector(tag="h1"),
)
LOCATION_SELECTORS = (PageSelector(attribute="class", value="ashby-job-posting-brief-location"),)
APPLY_SELECTORS = (PageSelector(tag="a", attribute="class", value="ashby-job-posting-apply-link"),)
