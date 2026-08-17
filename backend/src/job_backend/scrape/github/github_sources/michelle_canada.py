import httpx2

from job_backend.scrape.github.utils.download import download_file, raw_file_url
from job_backend.scrape.github.utils.json_links import collect_json_links
from job_backend.scrape.pipeline.models import FetchResult, JobSource, ScrapeResult

REPOSITORY = "michelleokolie/canada-tech-internships-summer-2027"
BRANCH = "add-internship-bot"
FILE_PATH = ".github/scripts/listings.json"
SOURCE = "michelle-canada-2027"
FEED_URL = raw_file_url(REPOSITORY, BRANCH, FILE_PATH)


def fetch_listings(
    etag: str | None, *, transport: httpx2.BaseTransport | None = None
) -> FetchResult:
    return download_file(REPOSITORY, BRANCH, FILE_PATH, etag, transport=transport)


def scrape_listings(payload: bytes) -> ScrapeResult:
    return collect_json_links(payload, FEED_URL)


ADAPTER = JobSource(name=SOURCE, fetch=fetch_listings, scrape=scrape_listings)
