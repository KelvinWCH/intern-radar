import httpx2
import pytest

from job_backend.scrape.utils.source_skips import source_unavailable

REQUEST = httpx2.Request("GET", "https://example.com/jobs")


@pytest.mark.parametrize(
    "error",
    [
        httpx2.HTTPStatusError(
            "Client error '403 Forbidden'",
            request=REQUEST,
            response=httpx2.Response(403, request=REQUEST),
        ),
        httpx2.ConnectError("[Errno -3] Temporary failure in name resolution", request=REQUEST),
        httpx2.ReadTimeout("The read operation timed out", request=REQUEST),
    ],
)
def test_bad_sites_skipped(error: Exception) -> None:
    assert source_unavailable(error)


@pytest.mark.parametrize(
    "error",
    [
        ValueError("Fictional parser bug"),
        KeyError("title"),
        RuntimeError("Scrape history record disappeared"),
    ],
)
def test_importer_failures_still_fail(error: Exception) -> None:
    assert not source_unavailable(error)
