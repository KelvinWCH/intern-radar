import json

from job_backend.jobs.details import edit_job_details
from job_backend.jobs.models import Job, JobEdit, JobResponse
from job_backend.jobs.retry import retry_saved_job
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.scrape.models import SourceState
from job_backend.scrape.pipeline.models import (
    FetchResult,
    JobLink,
    JobSource,
    RawDocument,
    ScrapeResult,
)
from job_backend.scrape.pipeline.pipeline import scrape_source
from job_backend.scrape.utils.browser_errors import BrowserAccessError
from job_backend.scrape.utils.robots import RobotsDisallowedError


def _blocked(_url: str) -> RawDocument:
    raise BrowserAccessError("Verify you are human")


def _page(url: str) -> RawDocument:
    return RawDocument(
        source_url=url,
        media_type="application/json",
        content=json.dumps(
            {
                "@type": "JobPosting",
                "title": "Software Intern",
                "hiringOrganization": {"name": "Example Company"},
                "jobLocation": {"address": {"addressLocality": "Toronto", "addressCountry": "CA"}},
                "description": "<p>Build Python APIs.</p><style>.bad {color:red}</style>",
                "url": url,
            }
        ),
    )


def _flagged(engine: Database) -> JobResponse:
    link = JobLink(
        url="https://example.com/jobs/1",
        listing_url="https://example.com/feed",
        date_posted=1,
        external_id="source-row",
        listing_data={
            "title": "Software Intern",
            "company": "Example Company",
            "location": "Toronto, Canada",
        },
    )
    source = JobSource(
        name="retry-fixture",
        fetch=lambda _etag: FetchResult(b"fixture", None),
        scrape=lambda _payload: ScrapeResult(fetched=1, links=[link]),
        require_recent_dates=False,
    )
    scrape_source(engine, source, fetch_page=_blocked)
    with Session(engine) as session:
        job = session.all(Job)[0]
        return JobResponse.model_validate(job)


def test_retry_keeps_edits(
    engine: Database,
) -> None:
    job = _flagged(engine)
    with Session(engine) as session:
        state = session.get(SourceState, job.source)
        assert state is not None
        previous_state = state.to_document()
        edited = edit_job_details(
            session,
            job.id,
            JobEdit(
                version=job.details_version,
                raw_description="My raw reference",
                cleaned_description="My reviewed requirements",
            ),
        )
        version = edited.details_version
    calls: list[str] = []

    def read(url: str) -> RawDocument:
        calls.append(url)
        return _page(url)

    result = retry_saved_job(engine, job.id, version, fetch_page=read)
    assert calls == [job.application_url]
    assert result.id == job.id and result.review_reason is None
    assert result.raw_description == "My raw reference"
    assert result.cleaned_description == "My reviewed requirements"
    assert result.details_version == version + 1
    assert result.first_seen_at == job.first_seen_at
    with Session(engine) as session:
        assert len(session.all(Job)) == 1
        state = session.get(SourceState, job.source)
        assert state is not None and state.to_document() == previous_state


def test_retry_blocked_by_robots(engine: Database) -> None:
    job = _flagged(engine)
    assert job.review_reason == "security_challenge"

    def disallowed(url: str) -> RawDocument:
        raise RobotsDisallowedError(url)

    result = retry_saved_job(engine, job.id, job.details_version, fetch_page=disallowed)
    assert result.review_reason == "robots_disallowed"
    with Session(engine) as session:
        assert session.all(Job)[0].review_reason == "robots_disallowed"
