from job_backend.persistence.database import Database
from job_backend.scrape.pipeline.cache import ScrapeCache
from job_backend.scrape.pipeline.challenges import ChallengeMemory

DAY = 86400


def _memory(engine: Database, now: int, *, enabled: bool = True) -> ChallengeMemory:
    return ChallengeMemory(ScrapeCache(engine), ["blocked.example"], now=now, enabled=enabled)


def test_two_challenges_skip(engine: Database) -> None:
    first = _memory(engine, 1_000_000)
    first.challenged("blocked.example")
    assert _memory(engine, 1_000_100).skipped("blocked.example") is None
    second = _memory(engine, 1_007_200)
    second.challenged("blocked.example")
    record = _memory(engine, 1_007_300).skipped("blocked.example")
    assert record is not None and record.streak == 2
    assert record.skip_until == 1_007_200 + DAY
    third = _memory(engine, 1_007_200 + DAY + 1)
    assert third.skipped("blocked.example") is None
    third.challenged("blocked.example")
    later = _memory(engine, 1_007_200 + DAY + 2).skipped("blocked.example")
    assert later is not None and later.skip_until == 1_007_200 + DAY + 1 + 3 * DAY


def test_streak_resets(engine: Database) -> None:
    _memory(engine, 1_000_000).challenged("blocked.example")
    recovered = _memory(engine, 1_003_600)
    recovered.readable("blocked.example")
    after = _memory(engine, 1_007_200)
    after.challenged("blocked.example")
    assert _memory(engine, 1_007_300).skipped("blocked.example") is None
    _memory(engine, 1_007_200 + 4 * DAY).challenged("blocked.example")
    assert _memory(engine, 1_007_200 + 4 * DAY + 1).skipped("blocked.example") is None
