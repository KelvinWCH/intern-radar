from functools import partial

import httpx2

from job_backend.scrape.github.utils.download import download_file, raw_file_url
from job_backend.scrape.github.utils.markdown_links import collect_markdown_links
from job_backend.scrape.pipeline.models import FetchResult, JobSource, ScrapeResult

REPOSITORY = "WonOfAKind/New-Grad-And-Internships-2027"
BRANCH = "main"
CATEGORY_FILES: dict[str, str] = {
    "aerospace": "internships/aerospace.md",
    "ai-ml": "internships/ai-ml.md",
    "data": "internships/data.md",
    "hardware-electrical": "internships/hardware-electrical.md",
    "manufacturing-industrial": "internships/manufacturing-industrial.md",
    "mechanical": "internships/mechanical.md",
    "other-engineering": "internships/other-engineering.md",
    "product-management": "internships/product-management.md",
    "software": "internships/software.md",
    "technical-writing": "internships/technical-writing.md",
}


def fetch_listings(
    category: str, etag: str | None, *, transport: httpx2.BaseTransport | None = None
) -> FetchResult:
    return download_file(REPOSITORY, BRANCH, CATEGORY_FILES[category], etag, transport=transport)


def scrape_listings(category: str, payload: bytes) -> ScrapeResult:
    return collect_markdown_links(
        payload,
        raw_file_url(REPOSITORY, BRANCH, CATEGORY_FILES[category]),
        required_columns=("Company", "Role"),
    )


ADAPTERS: tuple[JobSource, ...] = tuple(
    JobSource(
        name=f"won-{category}-2027",
        fetch=partial(fetch_listings, category),
        scrape=partial(scrape_listings, category),
    )
    for category in CATEGORY_FILES
)
