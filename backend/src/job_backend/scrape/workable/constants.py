from job_backend.scrape.pipeline.heuristics.models import PageSelector

API_ROOT = "https://apply.workable.com/api/v1/widget/accounts"
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
PLACE_FIELDS = frozenset({"city", "state", "country", "locations"})


PAGE_HOSTS = ("apply.workable.com",)
TITLE_SELECTORS = (PageSelector(attribute="data-ui", value="job-title"),)
LOCATION_SELECTORS = (PageSelector(attribute="data-ui", value="job-location"),)
COMPANY_SELECTORS = (PageSelector(attribute="data-ui", value="company-name"),)
APPLY_SELECTORS = (PageSelector(tag="a", attribute="data-ui", value="apply-button"),)
