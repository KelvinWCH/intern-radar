from collections.abc import Callable, Generator
from contextlib import contextmanager

import httpx2

from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.pipeline.models import JobPageSettings, RawDocument
from job_backend.scrape.pipeline.telemetry.performance import PerformanceTracker
from job_backend.scrape.utils.browser_errors import BrowserAccessError
from job_backend.scrape.utils.browser_fallback import BrowserReader, open_browser_reader
from job_backend.scrape.utils.constants import IMPORTER_USER_AGENT
from job_backend.scrape.utils.job_page_http import HttpPageStatusError, fetch_http_page
from job_backend.scrape.utils.job_readiness import has_structured_description
from job_backend.scrape.utils.models import BrowserReadOptions
from job_backend.scrape.utils.pacing import HostCooldownError, pace_request, track_response
from job_backend.scrape.utils.page_text import page_text
from job_backend.scrape.utils.posting_apis import read_posting_api


def _browser_page(url: str, *, reader: BrowserReader, settings: JobPageSettings) -> RawDocument:
    document = reader.read(
        url,
        BrowserReadOptions(max_page_bytes=settings.max_page_bytes, wait_for_job_content=True),
    )
    page_text(document.html)
    return RawDocument(
        content=document.html,
        source_url=document.url,
        media_type="text/html",
    )


@contextmanager
def open_page_reader(
    settings: JobPageSettings,
    *,
    browser_fallback: Callable[[str], RawDocument] | None = None,
    performance: PerformanceTracker | None = None,
) -> Generator[Callable[[str], RawDocument], None, None]:
    metrics = performance or PerformanceTracker()
    if settings.renderer in {"http", "auto"}:
        timeout = httpx2.Timeout(
            settings.timeout_seconds, connect=min(10.0, settings.timeout_seconds)
        )
        with (
            httpx2.Client(
                event_hooks={"request": [pace_request], "response": [track_response]},
                timeout=timeout,
                follow_redirects=False,
                headers={
                    "User-Agent": IMPORTER_USER_AGENT,
                    "Accept": "text/html,application/json",
                },
            ) as client,
            httpx2.Client(
                event_hooks={"request": [pace_request]},
                timeout=timeout,
                follow_redirects=False,
                headers={
                    "User-Agent": IMPORTER_USER_AGENT,
                    "Accept": "application/json",
                },
            ) as api_client,
        ):

            def read(url: str) -> RawDocument:
                record = read_posting_api(url, client=api_client, settings=settings)
                if record is not None:
                    metrics.event(f"Read {url} from its provider's public posting API")
                    return record
                try:
                    document = fetch_http_page(url, client=client, settings=settings)
                    if settings.renderer == "http" or has_structured_description(document):
                        return document
                except (BrowserAccessError, HttpPageStatusError, HostCooldownError):
                    raise
                except SourceDataError:
                    if settings.renderer == "http":
                        raise
                if browser_fallback is None:
                    raise SourceDataError(
                        "HTTP page needs browser rendering; use the pooled reader"
                    )
                metrics.increment("browser_fallbacks")
                metrics.event(f"{url} needs a real browser; opening it in Chrome")
                return browser_fallback(url)

            yield read
        return
    metrics.event("Launching headless Chrome")
    with open_browser_reader(settings) as reader:
        metrics.event("Chrome is ready")

        def read_browser(url: str) -> RawDocument:
            metrics.increment("browser_reads")
            metrics.event(f"Rendering {url} in Chrome")
            return _browser_page(url, reader=reader, settings=settings)

        yield read_browser
