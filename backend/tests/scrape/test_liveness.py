from dataclasses import replace

import pytest
from pytest import MonkeyPatch

from job_backend.jobs.identity import job_document_id
from job_backend.jobs.models import Job
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.models import SourceState
from job_backend.scrape.pipeline.models import (
    FetchFailure,
    FetchResult,
    JobSource,
    ScrapeRunResponse,
)
from job_backend.scrape.pipeline.pipeline import scrape_source
from tests.helpers import ADAPTER, StubNormalizer, listing, payload

BOARD = replace(ADAPTER, complete_listing=True)


CONFIRM_DELAY = "job_backend.scrape.pipeline.liveness.CONFIRM_AFTER_SECONDS"


@pytest.fixture(autouse=True)
def immediate_confirmation(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(CONFIRM_DELAY, 0)


def _import(
    engine: Database, normalizer: StubNormalizer, *ids: str, source: JobSource = BOARD
) -> ScrapeRunResponse:
    data = payload(*(listing(identity) for identity in ids))
    return scrape_source(
        engine, source, lambda _etag: FetchResult(data, None), normalizer=normalizer
    )


def _job(engine: Database, external_id: str, source: str = BOARD.name) -> Job:
    with Session(engine) as session:
        job = session.get(Job, job_document_id(source, external_id), hydrate=False)
        assert job is not None
        return job


def test_closes_after_two_misses(engine: Database, normalizer: StubNormalizer) -> None:
    _import(engine, normalizer, "a", "b", "c")
    _import(engine, normalizer, "a", "b")
    first_miss = _job(engine, "c")
    assert first_miss.active is True and first_miss.closed_reason is None
    with Session(engine) as session:
        state = session.get(SourceState, BOARD.name)
        assert state is not None
        assert list(state.missing_since) == [job_document_id(BOARD.name, "c")]
    version = first_miss.details_version
    _import(engine, normalizer, "a", "b")
    closed = _job(engine, "c")
    assert closed.active is False
    assert closed.closed_reason == "not_listed"
    assert closed.closed_at is not None
    assert closed.closed_detail == "No longer listed on the employer's job board."
    assert closed.details_version == version + 1
    assert _job(engine, "a").active is True
    with Session(engine) as session:
        state = session.get(SourceState, BOARD.name)
        assert state is not None and state.missing_since == {}


def test_returning_posting_reopens(engine: Database, normalizer: StubNormalizer) -> None:
    _import(engine, normalizer, "a", "b")
    _import(engine, normalizer, "a")
    _import(engine, normalizer, "a")
    assert _job(engine, "b").active is False
    _import(engine, normalizer, "a", "b")
    reopened = _job(engine, "b")
    assert reopened.active is not False
    assert reopened.closed_reason is reopened.closed_at is reopened.closed_detail is None


def test_partial_listing(engine: Database, normalizer: StubNormalizer) -> None:
    _import(engine, normalizer, "a", "b")
    partial = payload(listing("a"))
    failure = (FetchFailure(SourceDataError("page 2 failed"), "https://example.com/page/2"),)
    for _ in range(3):
        scrape_source(
            engine,
            BOARD,
            lambda _etag: FetchResult(partial, None, failure),
            normalizer=normalizer,
        )
    assert _job(engine, "b").active is True


def test_user_status_kept(engine: Database, normalizer: StubNormalizer) -> None:
    _import(engine, normalizer, "a", "b")
    with Session(engine) as session, session.begin():
        job = session.get(Job, job_document_id(BOARD.name, "b"), hydrate=False)
        assert job is not None
        job.detail_overrides = {"active": True}
    for _ in range(3):
        _import(engine, normalizer, "a")
    job = _job(engine, "b")
    assert job.active is True and job.closed_reason is None
