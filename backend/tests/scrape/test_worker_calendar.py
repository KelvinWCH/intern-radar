from datetime import datetime
from pathlib import Path
from threading import Event

import pytest

from job_backend.scrape.worker.calendar import next_clock_time
from job_backend.scrape.worker.models import (
    ScheduledScrape,
    SourceGroup,
    WorkerSettings,
)
from job_backend.scrape.worker.scheduler import next_due, run_schedule
from job_backend.scrape.worker.state import load_state


def _stamp(value: str) -> float:
    return datetime.fromisoformat(value).timestamp()


def _settings() -> WorkerSettings:
    return WorkerSettings(
        tasks=[
            ScheduledScrape(group="github", interval_hours=3),
            ScheduledScrape(group="companies", interval_hours=12, daily_hours=[3, 15]),
            ScheduledScrape(group="boards", interval_hours=24, daily_hours=[4]),
        ]
    )


def test_clock_tasks(tmp_path: Path) -> None:
    path = tmp_path / "worker-state.json"
    settings = _settings()
    calls: list[SourceGroup] = []
    now = _stamp("2026-10-19T02:00:00-04:00")

    def run(group: SourceGroup, *, resume_since: float | None = None) -> int:
        assert load_state(path).last_started[group] == now
        calls.append(group)
        return 0

    def cycle() -> None:
        assert (
            run_schedule(
                settings, load_state(path), path, Event(), run, once=True, clock=lambda: now
            )
            == 0
        )

    cycle()
    assert calls == ["github"]
    calls.clear()
    now = _stamp("2026-10-19T02:59:59-04:00")
    cycle()
    assert calls == []
    now = _stamp("2026-10-19T03:20:00-04:00")
    cycle()
    assert calls == ["companies"]
    calls.clear()
    now = _stamp("2026-10-19T04:00:00-04:00")
    cycle()
    assert calls == ["boards"]
    state = load_state(path)
    assert next_due(settings.tasks[1], state) == _stamp("2026-10-19T15:00:00-04:00")
    assert next_due(settings.tasks[2], state) == _stamp("2026-10-20T04:00:00-04:00")
    calls.clear()
    now = _stamp("2026-10-23T16:00:00-04:00")
    cycle()
    assert sorted(calls) == ["boards", "companies", "github"]
    calls.clear()
    cycle()
    assert calls == []


@pytest.mark.parametrize(
    ("previous", "expected", "elapsed_hours"),
    [
        ("2026-03-07T15:00:00-05:00", "2026-03-08T03:00:00-04:00", 11),
        ("2026-10-31T15:00:00-04:00", "2026-11-01T03:00:00-05:00", 13),
    ],
)
def test_daylight_saving(previous: str, expected: str, elapsed_hours: int) -> None:
    actual = next_clock_time([3, 15], "America/New_York", _stamp(previous), inclusive=False)
    assert actual == _stamp(expected)
    assert actual - _stamp(previous) == elapsed_hours * 3600
