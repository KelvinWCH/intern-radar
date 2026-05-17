from collections.abc import Generator
from contextlib import contextmanager
from functools import partial
from urllib.parse import urlsplit

from playwright.sync_api import Browser, Page, Route, sync_playwright
from playwright.sync_api import Error as BrowserError

from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.pipeline.models import JobPageSettings
from job_backend.scrape.utils.access_challenges import require_no_challenge
from job_backend.scrape.utils.browser_errors import BrowserUnavailableError
from job_backend.scrape.utils.constants import IMPORTER_USER_AGENT
from job_backend.scrape.utils.public_urls import require_public_url


def _public_request(route: Route, *, headless: bool) -> None:
    blocked = {"image", "font", "media"} if headless else {"media"}
    if route.request.resource_type in blocked:
        route.abort()
        return
    try:
        require_public_url(route.request.url)
    except SourceDataError:
        route.abort()
    else:
        route.continue_()


def require_open_page(url: str, title: str, headings: tuple[str, ...] = ()) -> None:
    path = urlsplit(url).path.casefold()
    require_no_challenge(url, (title, *headings))
    if path.startswith(("/login", "/sign-in")):
        raise SourceDataError("The website redirected to a sign-in page")


@contextmanager
def open_browser_page(settings: JobPageSettings) -> Generator[Page, None, None]:
    with sync_playwright() as runtime:
        channels = [settings.browser_channel]
        if (
            not settings.browser_headless
            and not settings.browser_channel
            and not settings.browser_executable
        ):
            channels = ["chrome", None]
        browser: Browser | None = None
        for channel in channels:
            try:
                browser = runtime.chromium.launch(
                    headless=settings.browser_headless,
                    chromium_sandbox=True,
                    channel=channel,
                    executable_path=settings.browser_executable,
                )
                break
            except BrowserError:
                continue
        if browser is None:
            raise BrowserUnavailableError(
                "Chromium could not start; install it with python -m playwright install chromium, "
                "or configure JOB_BROWSER_CHANNEL/JOB_BROWSER_EXECUTABLE. "
                "Visible mode also requires an available desktop session."
            )
        try:
            # keep the browser's own user agent and add ours, so the visit is never anonymous
            probe = browser.new_page()
            user_agent = f"{probe.evaluate('navigator.userAgent')} {IMPORTER_USER_AGENT}"
            probe.close()
            context = browser.new_context(
                accept_downloads=False, service_workers="block", user_agent=user_agent
            )
            context.route("**/*", partial(_public_request, headless=settings.browser_headless))
            context.route_web_socket("**/*", lambda _route: None)
            page = context.new_page()
            page.set_default_timeout(settings.timeout_seconds * 1000)
            yield page
        finally:
            browser.close()
