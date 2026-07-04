import httpx2
import pytest

from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.utils.http import download_feed

FEED_URL = "https://example.com/jobs.json"


def test_fetch_sends_etag_and_handles_304() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.headers["If-None-Match"] == '"previous"'
        return httpx2.Response(304)

    result = download_feed(FEED_URL, '"previous"', transport=httpx2.MockTransport(handler))
    assert result.payload is None
    assert result.etag == '"previous"'


def test_fetch_bounds_download_size() -> None:
    transport = httpx2.MockTransport(lambda _request: httpx2.Response(200, content=b"[]"))
    with pytest.raises(SourceDataError):
        download_feed(FEED_URL, None, transport=transport, max_bytes=1)
