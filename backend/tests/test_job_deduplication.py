from job_backend.jobs.duplicates import job_responses
from job_backend.jobs.models import Job
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.scrape.pipeline.models import FetchResult, JobSource
from job_backend.scrape.pipeline.pipeline import scrape_source
from tests.helpers import StubNormalizer, fixture_scrape, listing, payload


def _import(engine: Database, source: str, row: dict[str, object]) -> int:
    adapter = JobSource(
        name=source, fetch=lambda _etag: FetchResult(payload(row), None), scrape=fixture_scrape
    )
    return scrape_source(engine, adapter, normalizer=StubNormalizer()).created


def test_same_employer_id(engine: Database) -> None:
    first = listing("first-row")
    first.update(source_job_id="REQ-001", url="https://example.com/jobs/one")
    second = listing("second-row")
    second.update(source_job_id="REQ-001", url="https://example.com/jobs/two")
    assert _import(engine, "first-board", first) == 1
    assert _import(engine, "second-board", second) == 1
    with Session(engine) as session:
        jobs = list(session.find(Job, order_by=("source", "external_id")))
        assert len(jobs) == 2
        assert [(j.source, j.external_id) for j in jobs] == [
            ("first-board", "first-row"),
            ("second-board", "second-row"),
        ]
        responses = job_responses(session, jobs)
        assert responses[0].duplicated_jobs.items[0].id == jobs[1].id
        assert responses[0].duplicated_jobs.items[0].date_posted == jobs[1].date_posted
        assert responses[0].duplicated_jobs.items[0].match_reason == "same_employer_id"
        assert responses[1].duplicated_jobs.items[0].id == jobs[0].id


def test_same_id_other_company(engine: Database) -> None:
    first = listing("one")
    first["source_job_id"] = "123"
    second = listing("two")
    second.update(source_job_id="123", company_name="Another Company")
    assert _import(engine, "board-one", first) == _import(engine, "board-two", second) == 1
    with Session(engine) as session:
        assert len(session.find(Job)) == 2


def test_url_candidates(engine: Database) -> None:
    first = listing("one")
    first["url"] = "https://example.com/job?utm_source=repo-one"
    second = listing("two")
    second.update(url="https://example.com/job?utm_source=repo-two", source_job_id="R-42")
    third = listing("three")
    third.update(url="https://example.com/another-path", source_job_id="R-42")
    assert _import(engine, "one", first) == 1
    assert _import(engine, "two", second) == _import(engine, "three", third) == 1
    with Session(engine) as session:
        jobs = list(session.find(Job, order_by=("source", "external_id")))
        by_source = {job.source: job for job in jobs}
        assert len(jobs) == 3 and by_source["one"].source_job_id is None
        related = job_responses(session, [by_source["two"]])[0].duplicated_jobs.items
        assert {item.source: item.match_reason for item in related} == {
            "one": "same_url",
            "three": "same_employer_id",
        }
