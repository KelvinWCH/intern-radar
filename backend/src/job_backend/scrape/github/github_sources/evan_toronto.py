import time
from urllib.parse import urlsplit

import httpx2
from pydantic import JsonValue, TypeAdapter

from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.github.utils.dates import parse_posted_date
from job_backend.scrape.github.utils.download import download_file, raw_file_url
from job_backend.scrape.pipeline.models import (
    FetchResult,
    JobLink,
    JobSource,
    ScrapeResult,
)

REPOSITORY = "Evan-ASLO/internship-tracker-toronto"
BRANCH = "main"
FILE_PATH = "live_jobs.json"
SOURCE = "evan-toronto"
FEED_URL = raw_file_url(REPOSITORY, BRANCH, FILE_PATH)
AGGREGATOR_HOSTS = frozenset({"www.adzuna.ca", "adzuna.ca"})


def fetch_listings(
    etag: str | None, *, transport: httpx2.BaseTransport | None = None
) -> FetchResult:
    return download_file(REPOSITORY, BRANCH, FILE_PATH, etag, transport=transport)


def scrape_listings(payload: bytes) -> ScrapeResult:
    envelope = TypeAdapter(dict[str, JsonValue]).validate_json(payload, strict=True)
    records = TypeAdapter(list[dict[str, JsonValue]]).validate_python(
        envelope.get("jobs"), strict=True
    )
    if not records:
        raise SourceDataError("Refusing an unexpectedly empty Toronto tracker job list")
    links: list[JobLink] = []
    now = int(time.time())
    for record in records:
        url = record.get("url")
        if not isinstance(url, str) or not url or urlsplit(url).hostname in AGGREGATOR_HOSTS:
            continue
        listing = {key: value for key, value in record.items() if key != "content"}
        links.append(
            JobLink(
                url=url,
                listing_url=FEED_URL,
                date_posted=parse_posted_date(record.get("posted"), now=now),
                listing_data=listing,
            )
        )
    return ScrapeResult(fetched=len(records), links=links)


ADAPTER = JobSource(name=SOURCE, fetch=fetch_listings, scrape=scrape_listings)
