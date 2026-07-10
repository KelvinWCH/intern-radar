from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import cast
from unittest.mock import MagicMock

import pytest
from playwright.sync_api import Page
from pytest import MonkeyPatch

from job_backend.scrape.pipeline.models import JobPageSettings
from job_backend.scrape.utils import browser_fallback, browser_page
from job_backend.scrape.utils.browser_errors import BrowserAccessError
from job_backend.scrape.utils.browser_fallback import open_browser_reader
from job_backend.scrape.utils.models import BrowserReadOptions

URL = "https://jobs.example/intern"
OPTIONS = BrowserReadOptions(max_page_bytes=10000)


def _page(status: int = 200) -> MagicMock:
    page = MagicMock(spec=Page)
    page.url = URL
    page.is_closed.return_value = False
    page.goto.return_value.status = status
    page.title.return_value = "Internship" if status == 200 else "Just a moment..."
    page.content.return_value = "<h1>Internship</h1><p>Full job requirements</p>"
    page.locator.return_value.all_text_contents.return_value = []
    page.locator.return_value.inner_text.return_value = "Full job requirements"
    return page


@dataclass
class Browsers:
    pages: list[MagicMock]
    modes: list[bool] = field(default_factory=list[bool])
    closed: list[bool] = field(default_factory=list[bool])

    @contextmanager
    def open(self, settings: JobPageSettings) -> Generator[Page, None, None]:
        page = self.pages[len(self.modes)]
        self.modes.append(settings.browser_headless)
        try:
            yield cast(Page, page)
        finally:
            self.closed.append(settings.browser_headless)


def _install(monkeypatch: MonkeyPatch, *pages: MagicMock) -> Browsers:
    def public_url(_url: str) -> None:
        return None

    browsers = Browsers(list(pages))
    monkeypatch.setattr(browser_fallback, "open_browser_page", browsers.open)
    monkeypatch.setattr(browser_page, "require_public_url", public_url)
    return browsers


def test_readable_page_is_read_headless(monkeypatch: MonkeyPatch) -> None:
    browsers = _install(monkeypatch, _page())
    with open_browser_reader(JobPageSettings()) as reader:
        assert "Full job requirements" in reader.read(URL, OPTIONS).html
    assert browsers.modes == browsers.closed == [True]


def test_blocked_page_reported(monkeypatch: MonkeyPatch) -> None:
    page = _page(403)
    browsers = _install(monkeypatch, page)
    with open_browser_reader(JobPageSettings()) as reader:
        with pytest.raises(BrowserAccessError):
            reader.read(URL, OPTIONS)
    assert browsers.modes == browsers.closed == [True]
    assert page.goto.call_count == 1
