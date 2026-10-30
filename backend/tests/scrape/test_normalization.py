from job_backend.jobs.models import Job
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.scrape.pipeline.cache import ScrapeCache
from job_backend.scrape.pipeline.constants import EXTRACTION_CACHE_SECONDS
from job_backend.scrape.pipeline.models import (
    FetchResult,
    SharedExtraction,
)
from job_backend.scrape.pipeline.pipeline import scrape_source
from tests.helpers import ADAPTER, StubNormalizer, listing, payload


def test_cache_skips_unchanged(engine: Database) -> None:
    normalizer = StubNormalizer()
    data = payload(listing(), listing("second"))
    for _ in range(2):
        scrape_source(engine, ADAPTER, lambda _etag: FetchResult(data, None), normalizer=normalizer)
    assert normalizer.calls == 2
    changed = payload(listing(title="Changed Software Engineering Intern"), listing("second"))
    result = scrape_source(
        engine, ADAPTER, lambda _etag: FetchResult(changed, None), normalizer=normalizer
    )
    assert normalizer.calls == 3 and result.updated == 1 and result.unchanged == 1
    with Session(engine) as session:
        job = session.find(Job).first()
        assert job is not None and job.extraction_fingerprint is not None
    cached = ScrapeCache(engine).get(
        SharedExtraction,
        (job.extraction_fingerprint, normalizer.cache_key),
        ttl_seconds=EXTRACTION_CACHE_SECONDS,
    )
    assert cached is not None
    assert cached.document == {} and "jobs" in cached.result
    assert job.raw_description
    assert engine.gateway.find("normalization_cache", {}) == []
    assert engine.gateway.find("shared_extractions", {}) == []


def test_duplicate_ids_collapsed(engine: Database) -> None:
    normalizer = StubNormalizer()
    data = payload(listing(), listing())
    run = scrape_source(
        engine, ADAPTER, lambda _etag: FetchResult(data, None), normalizer=normalizer
    )
    assert normalizer.calls == 1 and run.created == 1
