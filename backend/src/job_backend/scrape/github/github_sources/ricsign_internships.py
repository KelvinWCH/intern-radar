import httpx2

from job_backend.scrape.github.utils.download import download_file, raw_file_url
from job_backend.scrape.github.utils.json_links import collect_json_links
from job_backend.scrape.pipeline.models import FetchResult, JobSource, ScrapeResult

REPOSITORY = "ricsign/Ricsign-New-Grads-Jobs-2027"
BRANCH = "main"
FILE_PATH = "data/v1/jobs.json"
SOURCE = "ricsign-2027"
FEED_URL = raw_file_url(REPOSITORY, BRANCH, FILE_PATH)


def fetch_listings(
    etag: str | None, *, transport: httpx2.BaseTransport | None = None
) -> FetchResult:
    return download_file(REPOSITORY, BRANCH, FILE_PATH, etag, transport=transport)


def scrape_listings(payload: bytes) -> ScrapeResult:
    return collect_json_links(
        payload,
        FEED_URL,
        records_key="jobs",
        id_key="uid",
        url_key="apply_url",
        date_key="posted_at",
    )


ADAPTER = JobSource(name=SOURCE, fetch=fetch_listings, scrape=scrape_listings)
