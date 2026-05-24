import json
import time
from collections.abc import Callable

import httpx2
import pytest

from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.github.utils.json_links import collect_json_links
from job_backend.scrape.models import ScrapeEvent, SourceState
from job_backend.scrape.pipeline.job_pages import JobPages
from job_backend.scrape.pipeline.models import (
    FetchResult,
    JobLink,
    JobPageSettings,
    JobSource,
    RawDocument,
)
from job_backend.scrape.pipeline.pipeline import scrape_source
from job_backend.scrape.utils.job_page_http import fetch_http_page
from tests.helpers import StubNormalizer, listing, payload


def _source(data: bytes) -> JobSource:
    return JobSource(
        name="url-first-fixture",
        fetch=lambda _etag: FetchResult(data, '"version"'),
        scrape=lambda raw: collect_json_links(raw, "https://example.com/github/jobs.json"),
    )


def _page_reader(calls: list[str]) -> Callable[[str], RawDocument]:
    def read(url: str) -> RawDocument:
        calls.append(url)
        row = listing(url.rsplit("/", 1)[-1])
        row.update(source_job_id="REQ-" + url.rsplit("/", 1)[-1], summary="Python and SQL.")
        return RawDocument(content=json.dumps(row), source_url=url)

    return read


@pytest.mark.parametrize("failure_type", [SourceDataError, RuntimeError, TimeoutError])
def test_failed_pages_continue(
    engine: Database, failure_type: type[Exception], caplog: pytest.LogCaptureFixture
) -> None:
    rows = [listing(f"{'failed' if index % 2 == 0 else 'good'}-{index}") for index in range(5)]
    for row in rows:
        row["date_posted"] = int(time.time()) - 60
    visited: list[str] = []
    good_page = _page_reader([])

    def read(url: str) -> RawDocument:
        visited.append(url)
        if "failed" in url:
            raise failure_type("Page unavailable; token=private")
        return good_page(url)

    source = _source(payload(*rows))
    result = scrape_source(
        engine,
        source,
        normalizer=StubNormalizer(),
        fetch_page=read,
        page_settings=JobPageSettings(http_concurrency=1),
    )
    assert len(visited) == 5 and result.created == 2
    assert result.status == "completed" and result.has_failures
    assert result.items_done == result.items_total == 5
    assert result.performance is not None and result.performance.failure_count == 3
    assert result.performance.page_failures == 3
    assert all(
        failure.error_type == failure_type.__name__ for failure in result.performance.failures
    )
    assert "private" not in result.model_dump_json() and "private" not in caplog.text
    assert "Could not read application page" in caplog.text
    assert all(record.levelname == "WARNING" for record in caplog.records)
    with Session(engine) as session:
        state = session.get(SourceState, source.name)
        assert state is not None and state.etag is None
        assert not session.find(ScrapeEvent, equal={"run_id": result.id, "level": "error"})


def test_date_gate_first(engine: Database) -> None:
    now = 1792267200
    links = [
        JobLink(
            url=f"https://example.com/{index}",
            listing_url="https://example.com/repo",
            date_posted=date,
        )
        for index, date in enumerate([now, now - 86400, now - 172800, now - 172801, None, now + 1])
    ]
    visited: list[str] = []
    documents = list(
        JobPages(engine, JobPageSettings(), fetch_page=_page_reader(visited), now=now).documents(
            links
        )
    )
    assert sorted(visited) == [
        "https://example.com/0",
        "https://example.com/1",
        "https://example.com/2",
    ]
    assert len(documents) == 3
    assert all(document.listing_url == "https://example.com/repo" for document in documents)


def test_private_redirect_blocked() -> None:
    requested: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requested.append(str(request.url))
        return httpx2.Response(302, headers={"location": "http://127.0.0.1/admin"})

    with httpx2.Client(transport=httpx2.MockTransport(handler), follow_redirects=False) as client:
        with pytest.raises(SourceDataError, match="non-public"):
            fetch_http_page(
                "https://example.com/apply",
                client=client,
                settings=JobPageSettings(),
                resolver=lambda host: ("127.0.0.1",) if host == "127.0.0.1" else ("1.1.1.1",),
            )
    assert requested == ["https://example.com/apply"]


def test_linkedin_links_flagged(engine: Database) -> None:
    now = 1792267200
    urls = [
        "https://www.linkedin.com/jobs/view/123",
        "https://ca.linkedin.com/jobs/view/456",
        "https://lnkd.in/abc",
        "https://example.com/789",
    ]
    links = [
        JobLink(url=url, listing_url="https://example.com/repo", date_posted=now) for url in urls
    ]
    visited: list[str] = []
    pages = JobPages(engine, JobPageSettings(), fetch_page=_page_reader(visited), now=now)
    assert pages.select(links) == links[3:]
    documents = list(pages.documents([*links, links[0]]))
    assert visited == ["https://example.com/789"] and len(documents) == 1
    assert pages.flagged_links == links[:3] and not pages.retry_needed
    assert pages.performance.snapshot().failure_count == 0


def test_linkedin_redirect_blocked() -> None:
    requested: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requested.append(str(request.url))
        return httpx2.Response(302, headers={"location": "https://www.linkedin.com/jobs/view/1"})

    with httpx2.Client(transport=httpx2.MockTransport(handler), follow_redirects=False) as client:
        with pytest.raises(SourceDataError, match="LinkedIn"):
            fetch_http_page(
                "https://example.com/apply",
                client=client,
                settings=JobPageSettings(),
                resolver=lambda _host: ("1.1.1.1",),
            )
    assert requested == ["https://example.com/apply"]
