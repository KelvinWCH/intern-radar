import pytest

from job_backend.jobs.models import Job
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.scrape.github.github_sources.simplify_internships import SOURCE
from job_backend.scrape.models import ScrapeRun, SourceState
from job_backend.scrape.pipeline.models import FetchResult
from job_backend.scrape.pipeline.pipeline import scrape_source
from tests.helpers import ADAPTER, StubNormalizer, listing, payload


def test_import_idempotent(engine: Database, normalizer: StubNormalizer) -> None:
    data = payload(listing())
    first = scrape_source(
        engine, ADAPTER, lambda _etag: FetchResult(data, '"first"'), normalizer=normalizer
    )
    second = scrape_source(
        engine, ADAPTER, lambda _etag: FetchResult(data, '"first"'), normalizer=normalizer
    )
    assert (first.created, second.created, second.unchanged) == (1, 0, 1)
    assert first.phase == "finished"
    assert first.items_total and first.items_done == first.items_total
    with Session(engine) as session, session.begin():
        saved = session.find(Job).first()
        assert saved is not None
        local_id = saved.id
        saved.summary = "Previously enriched description"
    changed = payload(listing(active=False, title="Updated internship"))
    third = scrape_source(
        engine, ADAPTER, lambda _etag: FetchResult(changed, '"second"'), normalizer=normalizer
    )
    assert third.updated == 1
    with Session(engine) as session:
        assert len(session.find(Job)) == 1
        saved = session.get(Job, local_id)
        assert saved is not None
        assert saved.title == "Updated internship"
        assert saved.active is False
        assert saved.summary == "Previously enriched description"


def test_malformed_record(engine: Database, normalizer: StubNormalizer) -> None:
    scrape_source(
        engine,
        ADAPTER,
        lambda _etag: FetchResult(payload(listing()), '"good"'),
        normalizer=normalizer,
    )
    invalid = listing("invalid")
    invalid["url"] = "javascript:alert(1)"
    bad_data = payload(listing("before"), invalid, listing("after"))
    result = scrape_source(
        engine, ADAPTER, lambda _etag: FetchResult(bad_data, '"bad"'), normalizer=normalizer
    )
    assert result.status == "completed" and result.created == 2 and result.has_failures
    assert result.items_done == result.items_total == 3
    assert result.performance is not None and result.performance.failure_count == 1
    assert result.performance.failures[0].error_type == "ValidationError"
    with Session(engine) as session:
        assert len(session.find(Job)) == 3
        state = session.get(SourceState, SOURCE)
        assert state is not None and state.etag is None


def test_conditional_fetch(engine: Database, normalizer: StubNormalizer) -> None:
    scrape_source(
        engine,
        ADAPTER,
        lambda _etag: FetchResult(payload(listing()), '"cached"'),
        normalizer=normalizer,
    )

    def unchanged(etag: str | None) -> FetchResult:
        assert etag == '"cached"'
        return FetchResult(None, etag)

    run = scrape_source(engine, ADAPTER, unchanged, normalizer=normalizer)
    assert run.status == "not_modified"
    assert run.created == 0
    assert run.items_done is None and run.items_total is None


def test_network_failure_is_recorded(engine: Database, normalizer: StubNormalizer) -> None:
    def broken(_etag: str | None) -> FetchResult:
        raise ConnectionError("Example upstream outage")

    with pytest.raises(ConnectionError):
        scrape_source(engine, ADAPTER, broken, normalizer=normalizer)
    with Session(engine) as session:
        run = session.find(ScrapeRun).first()
        assert run is not None and run.status == "failed"
        assert len(session.find(Job)) == 0


def test_absent_listing(engine: Database, normalizer: StubNormalizer) -> None:
    initial = payload(listing(), listing("still-present"))
    scrape_source(engine, ADAPTER, lambda _etag: FetchResult(initial, None), normalizer=normalizer)
    scrape_source(
        engine,
        ADAPTER,
        lambda _etag: FetchResult(payload(listing("still-present")), None),
        normalizer=normalizer,
    )
    with Session(engine) as session:
        original = session.find(Job, where=lambda row: row.external_id == "example-1").first()
        assert original is not None and original.active
