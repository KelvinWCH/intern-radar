from job_backend.scrape.pipeline.heuristics.models import PageSelector

PAGE_HOSTS = ("jobs.dayforcehcm.com",)
DESCRIPTION_SELECTOR = '[test-id="job-detail-body"]'
TITLE_SELECTORS = (PageSelector(attribute="test-id", value="job-detail-title"),)
LOCATION_SELECTORS = (PageSelector(attribute="test-id", value="job-detail-location-name"),)
REQUISITION_SELECTORS = (PageSelector(attribute="test-id", value="job-detail-job-req-id"),)
POSTED_SELECTORS = (PageSelector(attribute="test-id", value="job-detail-posted-date"),)
DESCRIPTION_SELECTORS = tuple(
    PageSelector(attribute="test-id", value=f"job-detail-{section}")
    for section in ("header", "body", "footer")
)
