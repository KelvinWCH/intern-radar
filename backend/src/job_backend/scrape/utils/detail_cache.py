import hashlib
import json
import random
import time
from collections.abc import Generator
from contextlib import contextmanager

from pydantic import JsonValue, TypeAdapter, ValidationError

from job_backend.persistence.database import Database
from job_backend.scrape.pipeline.cache import ScrapeCache
from job_backend.scrape.pipeline.models import ApiDetailCache

DETAIL_CACHE_MIN_SECONDS = 3 * 86400
DETAIL_CACHE_MAX_SECONDS = 7 * 86400
_DETAIL = TypeAdapter(dict[str, JsonValue])

_active_cache: ScrapeCache | None = None


@contextmanager
def detail_cache_scope(engine: Database) -> Generator[None]:
    global _active_cache
    previous = _active_cache
    _active_cache = ScrapeCache(engine)
    try:
        yield
    finally:
        _active_cache = previous


def _identity(url: str) -> tuple[str]:
    return (hashlib.sha256(url.encode()).hexdigest(),)


def cached_detail(url: str) -> dict[str, JsonValue] | None:
    cache = _active_cache
    if cache is None:
        return None
    record = cache.get(ApiDetailCache, _identity(url), ttl_seconds=DETAIL_CACHE_MAX_SECONDS)
    if record is None or record.url != url:
        return None
    try:
        return _DETAIL.validate_json(record.content)
    except ValidationError:
        return None


def store_detail(url: str, detail: dict[str, JsonValue]) -> None:
    cache = _active_cache
    if cache is None:
        return
    cache.put(
        ApiDetailCache(
            url_hash=_identity(url)[0],
            url=url,
            content=json.dumps(detail, ensure_ascii=False),
            fetched_at=int(time.time()),
        ),
        ttl_seconds=random.uniform(DETAIL_CACHE_MIN_SECONDS, DETAIL_CACHE_MAX_SECONDS),
    )
