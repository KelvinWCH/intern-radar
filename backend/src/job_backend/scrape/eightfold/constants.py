from job_backend.scrape.pipeline.heuristics.models import PageSelector

BOARD_DOMAINS = {
    "apply.careers.microsoft.com": "microsoft.com",
    "careers.qualcomm.com": "qualcomm.com",
}


PAGE_HOSTS = ("careers.qualcomm.com", "apply.careers.microsoft.com")
TITLE_SELECTORS = (
    PageSelector(
        tag="h2",
        attribute="class",
        value="position-title-",
        prefix=True,
        excluded_ancestor_id="similar-positions-carousel",
    ),
)
LOCATION_SELECTORS = (
    PageSelector(
        attribute="class",
        value="position-location-",
        prefix=True,
        excluded_ancestor_id="similar-positions-carousel",
    ),
)
APPLY_SELECTORS = (
    PageSelector(
        tag="a",
        attribute="href",
        value="/careers/apply?pid=",
        prefix=True,
        excluded_ancestor_id="similar-positions-carousel",
    ),
)
