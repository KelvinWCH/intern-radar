from job_backend.scrape.pipeline.heuristics.models import PageSelector

SEARCH_PATH = "/search/"
SEARCH_TERMS = ("intern", "internship", "student", '"co-op"', "coop")
# max 25 rows per page no matter what offset you ask for
PAGE_SIZE = 25
MAX_PAGES_PER_TERM = 20
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
JOB_PATH_PATTERN = r"^/job/[^/]+/(?P<id>\d+)/?$"


ROW_LINK = PageSelector(tag="a", attribute="class", value="jobTitle-link")
ROW_LOCATION = PageSelector(tag="span", attribute="class", value="jobLocation")
RESULT_COUNT = PageSelector(tag="span", attribute="class", value="paginationLabel")
SEARCH_FORM = PageSelector(attribute="class", value="keywordsearch-icon")
TITLE_SELECTORS = (
    PageSelector(attribute="itemprop", value="title"),
    PageSelector(tag="h1"),
)
DESCRIPTION_SELECTORS = (
    PageSelector(attribute="class", value="jobdescription"),
    PageSelector(attribute="itemprop", value="description"),
)
LOCATION_SELECTORS = (PageSelector(tag="span", attribute="class", value="jobGeoLocation"),)
POSTED_FORMAT = "%a %b %d %H:%M:%S %Z %Y"
