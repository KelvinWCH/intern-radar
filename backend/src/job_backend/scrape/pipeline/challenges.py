from collections.abc import Iterable
from threading import Lock

from job_backend.scrape.pipeline.cache import ScrapeCache
from job_backend.scrape.pipeline.constants import (
    FIRST_SKIP_SECONDS,
    MAX_SKIP_SECONDS,
    MEMORY_SECONDS,
    SKIP_AFTER_STREAK,
    STREAK_WINDOW_SECONDS,
)
from job_backend.scrape.pipeline.models import ChallengedHost


class ChallengeMemory:
    def __init__(
        self, cache: ScrapeCache, hosts: Iterable[str], *, now: int, enabled: bool
    ) -> None:
        self.cache = cache
        self.now = now
        self.enabled = enabled
        self.lock = Lock()
        self.records: dict[str, ChallengedHost] = {}
        self.updated: set[str] = set()
        if enabled:
            for host in set(hosts):
                record = cache.get(ChallengedHost, (host,), ttl_seconds=MEMORY_SECONDS)
                if record is not None:
                    self.records[host] = record

    def skipped(self, host: str) -> ChallengedHost | None:
        record = self.records.get(host)
        return record if record is not None and record.skip_until > self.now else None

    # a site that keeps showing a bot check gets skipped for a while (1 day, 3 days, a week)
    # we never try to get past the check, we just back off
    def challenged(self, host: str) -> None:
        if not self.enabled or not host:
            return
        with self.lock:
            if host in self.updated:
                return
            self.updated.add(host)
            previous = self.records.get(host)
            streak = (
                previous.streak + 1
                if previous is not None
                and previous.streak
                and self.now - previous.last_challenge_at <= STREAK_WINDOW_SECONDS
                else 1
            )
            skip = (
                0
                if streak < SKIP_AFTER_STREAK
                else min(FIRST_SKIP_SECONDS * 3 ** (streak - SKIP_AFTER_STREAK), MAX_SKIP_SECONDS)
            )
            record = ChallengedHost(
                host=host, streak=streak, last_challenge_at=self.now, skip_until=self.now + skip
            )
            self.records[host] = record
        self.cache.put(record, ttl_seconds=MEMORY_SECONDS)

    def readable(self, host: str) -> None:
        if not self.enabled or not host:
            return
        with self.lock:
            previous = self.records.get(host)
            if previous is None or not previous.streak or host in self.updated:
                return
            self.updated.add(host)
            record = ChallengedHost(host=host)
            self.records[host] = record
        self.cache.put(record, ttl_seconds=MEMORY_SECONDS)
