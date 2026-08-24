import time

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

REPOSITORY = "Emjumaev/FAANG-2027-Internships-Tracker"
BRANCH = "scraper"
FILE_PATH = "data/jobs.json"
SOURCE = "emjumaev-2027"
FEED_URL = raw_file_url(REPOSITORY, BRANCH, FILE_PATH)


def fetch_listings(
    etag: str | None, *, transport: httpx2.BaseTransport | None = None
) -> FetchResult:
    return download_file(REPOSITORY, BRANCH, FILE_PATH, etag, transport=transport)


def scrape_listings(payload: bytes) -> ScrapeResult:
    envelope = TypeAdapter(dict[str, JsonValue]).validate_json(payload, strict=True)
    records = TypeAdapter(dict[str, dict[str, JsonValue]]).validate_python(
        envelope.get("jobs"), strict=True
    )
    if not records:
        raise SourceDataError("Refusing an unexpectedly empty Emjumaev job list")
    links: list[JobLink] = []
    now = int(time.time())
    for identifier, record in records.items():
        active = record.get("active")
        if not isinstance(active, bool):
            raise SourceDataError("Emjumaev job requires an explicit boolean active flag")
        if not active:
            continue
        url = record.get("url")
        if not isinstance(url, str) or not url:
            raise SourceDataError("Emjumaev active job requires an application URL")
        links.append(
            JobLink(
                url=url,
                listing_url=FEED_URL,
                date_posted=parse_posted_date(record.get("posted"), now=now),
                external_id=identifier,
                listing_data=record,
            )
        )
    return ScrapeResult(fetched=len(records), links=links)


ADAPTER = JobSource(name=SOURCE, fetch=fetch_listings, scrape=scrape_listings)
