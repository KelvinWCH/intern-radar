from job_backend.scrape.pipeline.heuristics.models import PageSelector

SEARCH_TERMS = ("intern", "internship", "student", '"co-op"')
MAX_PAGES_PER_TERM = 25
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
JOB_PATH_PATTERN = r"/JobDetail/[^/?#]+/(?P<id>\d+)/?$"


NEXT_PAGE = PageSelector(tag="a", attribute="class", value="paginationNextLink")
ITEM_LOCATION = PageSelector(attribute="class", value="list-item-location")
LIST_FIELD = PageSelector(attribute="class", value="article__content__field")
LIST_FIELD_LABEL = PageSelector(attribute="class", value="article__content__field__label")
LIST_FIELD_VALUE = PageSelector(attribute="class", value="article__content__field__value")
DETAIL_FIELD = PageSelector(attribute="class", value="article__content__view__field")
DETAIL_FIELD_LABEL = PageSelector(attribute="class", value="article__content__view__field__label")
DETAIL_FIELD_VALUE = PageSelector(attribute="class", value="article__content__view__field__value")
DETAILS = PageSelector(tag="article", attribute="class", value="article--details")
TITLE = PageSelector(tag="meta", attribute="property", value="og:title")
LOCATION_LABEL = r"\blocation"
REQUISITION_LABEL = r"\b(?:ref(?:erence)?|req(?:uisition)?|job\s*(?:id|number))\b"
