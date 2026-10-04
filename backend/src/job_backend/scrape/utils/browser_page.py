from playwright.sync_api import Error as BrowserError
from playwright.sync_api import Page, Response
from playwright.sync_api import TimeoutError as BrowserTimeout

from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.pipeline.heuristics.pages import description_selector
from job_backend.scrape.utils.browser import require_open_page
from job_backend.scrape.utils.browser_errors import BrowserAccessError, BrowserRetryableError
from job_backend.scrape.utils.constants import JOB_READY_SCRIPT
from job_backend.scrape.utils.job_page_http import HttpPageStatusError
from job_backend.scrape.utils.models import BrowserDocument, BrowserReadOptions
from job_backend.scrape.utils.pacing import observe_response, wait_for_request
from job_backend.scrape.utils.public_urls import require_public_url
from job_backend.scrape.utils.robots import require_robots_allowed


class BrowserTab:
    def __init__(self, page: Page) -> None:
        self.page = page
        self.status: int | None = None
        page.on("response", self._response)

    def _response(self, response: Response) -> None:
        if response.request.is_navigation_request() and response.frame == self.page.main_frame:
            self.status = response.status
            observe_response(response.url, response.status, response.header_value("retry-after"))

    def navigate(self, url: str, options: BrowserReadOptions) -> BrowserDocument:
        require_public_url(url)
        require_robots_allowed(url)
        wait_for_request(url)
        self.status = None
        try:
            response = self.page.goto(url, wait_until="domcontentloaded")
            if response is not None:
                self.status = response.status
            # the browser follows redirects itself, so the page it landed on is checked after
            if self.page.url != url:
                require_robots_allowed(self.page.url)
            require_open_page(self.page.url, self.page.title())
            if self.status in {401, 403}:
                denied = BrowserAccessError(f"Website denied access (HTTP {self.status})")
                denied.url = self.page.url
                raise denied
            try:
                if options.ready_selector:
                    self.page.locator(options.ready_selector).first.wait_for(
                        state="attached", timeout=8000
                    )
                elif options.wait_for_job_content:
                    self.page.wait_for_function(
                        JOB_READY_SCRIPT, arg=description_selector(url), polling=250, timeout=8000
                    )
                elif options.wait_for_network_idle:
                    self.page.wait_for_load_state("networkidle", timeout=10000)
            except BrowserTimeout:
                pass
            return self.snapshot(options)
        except BrowserAccessError:
            observe_response(url, 403)
            raise
        except BrowserError:
            raise BrowserRetryableError(f"Browser navigation failed or timed out: {url}") from None

    def snapshot(self, options: BrowserReadOptions, *, timeout_ms: float = 2000) -> BrowserDocument:
        try:
            require_public_url(self.page.url)
            html = self.page.content()
            if len(html.encode()) > options.max_page_bytes:
                raise SourceDataError("Rendered page exceeds its configured HTML size limit")
            if (
                self.status is not None
                and 400 <= self.status < 500
                and self.status not in {401, 403}
            ):
                raise SourceDataError(f"Page returned HTTP {self.status}")
            headings = tuple(self.page.locator("h1, h2").all_text_contents())
            body = self.page.locator("body").inner_text(timeout=min(2000, timeout_ms)).strip()
            labels = (*headings, *body.splitlines()) if len(body) < 4000 else headings
            require_open_page(self.page.url, self.page.title(), labels)
            if self.status in {401, 403}:
                denied = BrowserAccessError(f"Website denied access (HTTP {self.status})")
                denied.url = self.page.url
                raise denied
            if self.status == 503:
                raise HttpPageStatusError(503)
            if self.status is None or self.status >= 500:
                raise BrowserRetryableError(f"Page returned HTTP {self.status or 'no response'}")
            if not 200 <= self.status < 300:
                raise SourceDataError(f"Page returned HTTP {self.status}")
            if not body:
                raise BrowserRetryableError("The browser page is empty")
            document = BrowserDocument(url=self.page.url, html=html)
            selector = description_selector(document.url) if options.wait_for_job_content else None
            if (
                selector
                and len(
                    self.page.locator(selector).inner_text(timeout=min(2000, timeout_ms)).strip()
                )
                < 200
            ):
                raise BrowserRetryableError("The job description has not finished loading")
            if options.validate is not None:
                options.validate(document)
            return document
        except BrowserError:
            raise BrowserRetryableError("Browser page is unavailable or still loading") from None
