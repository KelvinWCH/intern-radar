import pytest

from job_backend.jobs.link_check import check_posting, check_saved_job
from job_backend.jobs.models import Job
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.scrape.pipeline.models import RawDocument
from job_backend.scrape.utils.job_page_http import HttpPageStatusError

NOW = 1_800_000_000
URL = "https://jobs.example.com/postings/42"


def _page(body: str, url: str = URL, media_type: str = "text/html") -> RawDocument:
    return RawDocument(content=body, source_url=url, media_type=media_type)


def test_missing_page_is_closed() -> None:
    def missing(_url: str) -> RawDocument:
        raise HttpPageStatusError(404)

    check = check_posting(URL, fetch_page=missing, now=NOW)
    assert check.status == "closed" and "HTTP 404" in check.detail
    assert check.checked_at == NOW and check.url == URL


@pytest.mark.parametrize(
    ("final_url", "body"),
    [
        ("https://job-boards.greenhouse.io/example?error=true", "<p>Current openings</p>"),
        ("https://jobs.example.com/errorpage/", "<p>Something went wrong</p>"),
        (URL, "<h1>Sorry, this job is no longer available.</h1>"),
    ],
)
def test_closed_notices(final_url: str, body: str) -> None:
    check = check_posting(URL, fetch_page=lambda _url: _page(body, final_url), now=NOW)
    assert check.status == "closed"
    assert check.final_url == (final_url if final_url != URL else None)


def _saved(engine: Database, **fields: object) -> str:
    with Session(engine) as session, session.begin():
        job = Job(
            id="job-check",
            source="greenhouse-example",
            external_id="42",
            company="Example",
            title="Intern",
            application_url=URL,
            active=None,
            job_hash="0" * 64,
            content_hash="0" * 64,
        )
        for name, value in fields.items():
            setattr(job, name, value)
        session.add(job)
    return "job-check"


def test_closed_check_marks_the_job_closed(engine: Database) -> None:
    job_id = _saved(engine)
    response = check_saved_job(
        engine, job_id, fetch_page=lambda _url: _page("<p>Position has been filled.</p>")
    )
    assert response.active is False
    assert response.closed_reason == "link_check"
    assert response.closed_detail == 'The page says "position has been filled".'
    assert response.link_check is not None and response.link_check.status == "closed"
