import time

import httpx2
import pytest

from job_backend.jobs.models import Job
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.scrape.models import SourceState
from job_backend.scrape.pipeline.job_pages import JobPages
from job_backend.scrape.pipeline.models import (
    FetchResult,
    JobLink,
    JobPageSettings,
    JobSource,
    RawDocument,
    ScrapeResult,
)
from job_backend.scrape.pipeline.pipeline import scrape_source
from job_backend.scrape.utils.browser_errors import BrowserAccessError
from job_backend.scrape.utils.job_page_http import HttpPageStatusError, fetch_http_page
from job_backend.scrape.utils.robots import RobotsDisallowedError
from tests.helpers import StubNormalizer


def _link(external_id: str | None = "example-1") -> JobLink:
    return JobLink(
        url="https://example.com/jobs/example-1",
        listing_url="https://example.com/board",
        external_id=external_id,
        date_posted=int(time.time()) - 60,
        listing_data={
            "company_name": "Listed Company",
            "title": "Listed internship",
            "locations": ["Toronto, ON, Canada"],
        },
    )


def _source(link: JobLink, name: str = "flagged-fixture") -> JobSource:
    return JobSource(
        name=name,
        fetch=lambda _etag: FetchResult(b"fixture", '"version"'),
        scrape=lambda _raw: ScrapeResult(fetched=1, links=[link]),
        terms=("Summer 2027",),
    )


@pytest.mark.parametrize("status", [200, 403])
@pytest.mark.parametrize(
    ("body", "media_type"),
    [
        ("<title>Just a moment...</title><div>Checking browser</div>", "text/html"),
        ("<h1>Verify <span>you are</span> human</h1>", "text/html"),
    ],
)
def test_detects_challenges(status: int, body: str, media_type: str) -> None:
    with httpx2.Client(
        transport=httpx2.MockTransport(
            lambda _request: httpx2.Response(
                status, text=body, headers={"content-type": media_type}
            )
        )
    ) as client:
        with pytest.raises(BrowserAccessError):
            fetch_http_page(
                "https://example.com/jobs/1",
                client=client,
                settings=JobPageSettings(renderer="http"),
                resolver=lambda _host: ("1.1.1.1",),
            )


@pytest.mark.parametrize("kind", ["challenge", "401", "403"])
def test_collects_blocked_links(engine: Database, kind: str) -> None:
    link = _link()
    error: Exception
    if kind == "challenge":
        error = BrowserAccessError("Security challenge")
    else:
        error = HttpPageStatusError(int(kind))

    def read(_url: str) -> RawDocument:
        raise error

    pages = JobPages(engine, JobPageSettings(renderer="http"), fetch_page=read)
    assert list(pages.documents([link])) == []
    assert pages.retry_needed
    assert pages.flagged_links == [link]


def test_linkedin_flagged(engine: Database, normalizer: StubNormalizer) -> None:
    link = _link().model_copy(update={"url": "https://www.linkedin.com/jobs/view/123"})
    source = _source(link)

    def never_read(_url: str) -> RawDocument:
        pytest.fail("LinkedIn must never be requested")

    first = scrape_source(engine, source, normalizer=normalizer, fetch_page=never_read)
    assert first.created == 1 and not first.has_failures and normalizer.calls == 0
    assert first.items_done == first.items_total == 0
    with Session(engine) as session, session.begin():
        job = session.all(Job)[0]
        assert job.review_reason == "linkedin_blocked"
        assert job.company == "Listed Company" and job.title == "Listed internship"
        assert job.application_url == link.url and job.raw_description is None
        state = session.get(SourceState, source.name)
        assert state is not None and state.etag == '"version"'
        job.review_reason = None

    second = scrape_source(engine, source, normalizer=normalizer, fetch_page=never_read)
    assert (second.created, second.updated, second.unchanged) == (0, 0, 1)
    with Session(engine) as session:
        assert session.all(Job)[0].review_reason is None


def test_robots_blocked_flagged(engine: Database, normalizer: StubNormalizer) -> None:
    link = _link()
    source = _source(link)

    def disallowed(url: str) -> RawDocument:
        raise RobotsDisallowedError(url)

    first = scrape_source(engine, source, normalizer=normalizer, fetch_page=disallowed)
    assert first.created == 1 and not first.has_failures and normalizer.calls == 0
    with Session(engine) as session, session.begin():
        job = session.all(Job)[0]
        assert job.review_reason == "robots_disallowed"
        assert job.company == "Listed Company" and job.title == "Listed internship"
        assert job.application_url == link.url and job.raw_description is None
        job.review_reason = None

    second = scrape_source(engine, source, normalizer=normalizer, fetch_page=disallowed)
    assert (second.created, second.updated, second.unchanged) == (0, 0, 1)
    with Session(engine) as session:
        assert session.all(Job)[0].review_reason is None


def test_robots_block_replaces_challenge_flag(engine: Database) -> None:
    link = _link()
    source = _source(link)

    def challenged(_url: str) -> RawDocument:
        raise BrowserAccessError("Security challenge")

    def disallowed(url: str) -> RawDocument:
        raise RobotsDisallowedError(url)

    scrape_source(engine, source, normalizer=StubNormalizer(), fetch_page=challenged)
    scrape_source(engine, source, normalizer=StubNormalizer(), fetch_page=disallowed)
    with Session(engine) as session:
        assert session.all(Job)[0].review_reason == "robots_disallowed"
