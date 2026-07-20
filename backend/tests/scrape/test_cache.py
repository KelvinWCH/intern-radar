import sqlite3
from contextlib import closing

import pytest

from job_backend.persistence.database import Database
from job_backend.scrape.pipeline.cache import ScrapeCache
from job_backend.scrape.pipeline.models import SharedExtraction


def test_cache_expiry(engine: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    now = [100.0]
    monkeypatch.setattr("job_backend.scrape.pipeline.cache.time.time", lambda: now[0])
    cache = ScrapeCache(engine)
    record = SharedExtraction(fingerprint="input", normalizer_key="v1")
    cache.put(record, ttl_seconds=10)
    now[0] = 111.0
    assert cache.get(SharedExtraction, ("input", "v1"), ttl_seconds=10) is None
    cache.put(record, ttl_seconds=10)
    with closing(sqlite3.connect(cache.path)) as connection, connection:
        connection.execute("UPDATE entries SET payload = ?", (b"broken",))
    assert cache.get(SharedExtraction, ("input", "v1"), ttl_seconds=10) is None
    cache.put(record, ttl_seconds=0)
    assert cache.get(SharedExtraction, ("input", "v1"), ttl_seconds=0) is None


def test_cache_eviction(engine: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("job_backend.scrape.pipeline.cache.MAX_CACHE_BYTES", 150)
    cache = ScrapeCache(engine)
    first = SharedExtraction(fingerprint="first", normalizer_key="v1")
    second = SharedExtraction(fingerprint="second", normalizer_key="v1")
    cache.put(first, ttl_seconds=60)
    assert cache.get(SharedExtraction, ("first", "v1"), ttl_seconds=60) == first
    cache.put(second, ttl_seconds=60)
    assert cache.get(SharedExtraction, ("first", "v1"), ttl_seconds=60) is None
    assert cache.get(SharedExtraction, ("second", "v1"), ttl_seconds=60) == second
