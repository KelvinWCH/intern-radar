from collections.abc import Generator
from contextlib import ExitStack, contextmanager

from job_backend.common.logger import get_logger
from job_backend.scrape.pipeline.models import JobPageSettings
from job_backend.scrape.utils.browser import open_browser_page
from job_backend.scrape.utils.browser_page import BrowserTab
from job_backend.scrape.utils.models import BrowserDocument, BrowserReadOptions

logger = get_logger(__name__)


class BrowserReader:
    def __init__(self, settings: JobPageSettings) -> None:
        self.settings = settings
        self.headless = settings.browser_headless
        self.resources = ExitStack()
        self.tab: BrowserTab | None = None

    def close(self) -> None:
        self.resources.close()
        self.tab = None

    def _tab(self) -> BrowserTab:
        if self.tab is None:
            settings = self.settings.model_copy(update={"browser_headless": self.headless})
            self.tab = BrowserTab(self.resources.enter_context(open_browser_page(settings)))
        return self.tab

    def read(self, url: str, options: BrowserReadOptions) -> BrowserDocument:
        return self._tab().navigate(url, options)


@contextmanager
def open_browser_reader(settings: JobPageSettings) -> Generator[BrowserReader, None, None]:
    reader = BrowserReader(settings)
    try:
        yield reader
    finally:
        reader.close()
