import re

from job_backend.scrape.pipeline.heuristics.models import PageSelector

PAGE_SIZE = 20
MAX_LISTING_PAGES = 500
LISTING_RESULT_CAP = 2000
PARTITION_FACETS = ("jobFamilyGroup", "jobFamily", "workerSubType", "timeType")
COUNTRY_FACETS = frozenset(
    {
        "country",
        "countryregion",
        "locationhierarchy1",
        "location_country",
        "locationcountry",
        "country_and_jurisdiction",
    }
)
LOCATION_FACETS = frozenset({"locations", "primarylocation", "location"})
LOCATION_FILTER_MIN_TOTAL = 200
PROVINCE_CODES = r"(?:ON|QC|BC|AB|MB|SK|NS|NB|NL|PE|NT|NU|YT)"
STUDENT_FACET_VALUE = r"\b(?:interns?|internships?|co-?ops?|coop|students?|stagiaires?)\b"
MAINTENANCE_HOST = "community.workday.com"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024
DETAIL_WORKERS = 3
DETAIL_BATCH_DELAY_SECONDS = 1.0
MAX_REQUEST_ATTEMPTS = 4
RETRY_BASE_SECONDS = 5.0
MAX_RETRY_DELAY_SECONDS = 60.0
RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504, 520})
PUBLIC_HOST_PATTERN = r"^(?P<tenant>[a-zA-Z0-9-]+)\.wd\d+\.myworkdayjobs\.com$"
SITE_PATTERN = r"^[a-zA-Z0-9_.-]+$"


PAGE_HOST_SUFFIX = ".myworkdayjobs.com"
TITLE_SELECTORS = (PageSelector(attribute="data-automation-id", value="jobPostingHeader"),)
LOCATION_SELECTORS = (
    PageSelector(attribute="data-automation-id", value="locations"),
    PageSelector(attribute="data-automation-id", value="location"),
)
IDENTIFIER_SELECTORS = (PageSelector(attribute="data-automation-id", value="requisitionId"),)
DATE_SELECTORS = (PageSelector(attribute="data-automation-id", value="postedOn"),)
APPLY_SELECTORS = (PageSelector(tag="a", attribute="data-automation-id", value="adventureButton"),)


LEGAL_EMPLOYER = "1390 Roche Services Europe Ltd"
REMOTE_ELIGIBILITY = re.compile(
    r"\bwe provide fully remote working conditions within (?P<country>Hungary)\b",
    re.IGNORECASE,
)
