import httpx2

from job_backend.scrape.github.utils.download import download_file, raw_file_url
from job_backend.scrape.github.utils.markdown_links import collect_markdown_links
from job_backend.scrape.pipeline.models import FetchResult, JobSource, ScrapeResult

REPOSITORY = "jobright-ai/2026-Design-Internship"
BRANCH = "master"
FILE_PATH = "README.md"
SOURCE = "jobright-design-internships"
FEED_URL = raw_file_url(REPOSITORY, BRANCH, FILE_PATH)


def fetch_listings(
    etag: str | None, *, transport: httpx2.BaseTransport | None = None
) -> FetchResult:
    return download_file(REPOSITORY, BRANCH, FILE_PATH, etag, transport=transport)


def scrape_listings(payload: bytes) -> ScrapeResult:
    return collect_markdown_links(payload, FEED_URL, required_columns=("Company", "Job Title"))


ADAPTER = JobSource(name=SOURCE, fetch=fetch_listings, scrape=scrape_listings)
