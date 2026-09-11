import httpx2

from job_backend.scrape.github.utils.download import download_file, raw_file_url
from job_backend.scrape.github.utils.markdown_links import collect_markdown_links
from job_backend.scrape.pipeline.models import FetchResult, JobSource, ScrapeResult

REPOSITORY = "Francklin9999/canada-internship"
BRANCH = "master"
FILE_PATH = "INTERNSHIPS.md"
SOURCE = "francklin-canada"
FEED_URL = raw_file_url(REPOSITORY, BRANCH, FILE_PATH)


def fetch_listings(
    etag: str | None, *, transport: httpx2.BaseTransport | None = None
) -> FetchResult:
    return download_file(REPOSITORY, BRANCH, FILE_PATH, etag, transport=transport)


def scrape_listings(payload: bytes) -> ScrapeResult:
    return collect_markdown_links(payload, FEED_URL, required_columns=("Company", "Role"))


ADAPTER = JobSource(name=SOURCE, fetch=fetch_listings, scrape=scrape_listings)
