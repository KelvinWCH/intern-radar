import time

import httpx2

from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.pipeline.models import FetchResult
from job_backend.scrape.utils.constants import (
    DEFAULT_MAX_BYTES,
    FEED_DOWNLOAD_SECONDS,
    IMPORTER_USER_AGENT,
    REQUEST_TIMEOUT,
)
from job_backend.scrape.utils.pacing import pace_request, track_response


def download_feed(
    url: str,
    etag: str | None,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    accept: str = "*/*",
    transport: httpx2.BaseTransport | None = None,
) -> FetchResult:
    if max_bytes <= 0:
        raise ValueError("The download byte limit must be positive")
    headers = {"User-Agent": IMPORTER_USER_AGENT, "Accept": accept}
    if etag:
        headers["If-None-Match"] = etag
    with (
        httpx2.Client(
            transport=transport,
            timeout=REQUEST_TIMEOUT,
            event_hooks={"request": [pace_request], "response": [track_response]},
        ) as client,
        client.stream("GET", url, headers=headers) as response,
    ):
        if response.status_code == 304:
            return FetchResult(payload=None, etag=etag)
        response.raise_for_status()
        chunks: list[bytes] = []
        size = 0
        deadline = time.monotonic() + FEED_DOWNLOAD_SECONDS
        for chunk in response.iter_bytes():
            if time.monotonic() > deadline:
                raise httpx2.ReadTimeout(
                    f"Feed download took longer than {FEED_DOWNLOAD_SECONDS:g} seconds",
                    request=response.request,
                )
            size += len(chunk)
            if size > max_bytes:
                raise SourceDataError(f"Feed exceeded the {max_bytes} byte size limit")
            chunks.append(chunk)
        return FetchResult(payload=b"".join(chunks), etag=response.headers.get("etag"))
