import os

import httpx2
import pytest
from pytest import MonkeyPatch

from job_backend.scrape.utils import pacing
from job_backend.scrape.utils.http import download_feed
from job_backend.scrape.utils.models import ScrapePacingSettings
from job_backend.scrape.utils.pacing import HostCooldownError, RequestPacer


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def read(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _pacer(clock: FakeClock) -> RequestPacer:
    return RequestPacer(
        ScrapePacingSettings(),
        clock=clock.read,
        sleep=clock.sleep,
        jitter=lambda low, high: (low + high) / 2,
        wall_clock=lambda: 0.0,
    )


def test_host_spacing(
    monkeypatch: MonkeyPatch,
) -> None:
    clock = FakeClock()
    monkeypatch.setattr(pacing, "_active_pacer", _pacer(clock))
    requested: list[str] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        requested.append(request.url.host)
        if request.url.host == "busy.example":
            return httpx2.Response(429, headers={"Retry-After": "1200"})
        return httpx2.Response(200, content=b"jobs")

    transport = httpx2.MockTransport(respond)
    assert download_feed("https://one.example/jobs", None, transport=transport).payload == b"jobs"
    assert download_feed("https://two.example/jobs", None, transport=transport).payload == b"jobs"
    assert download_feed("https://one.example/more", None, transport=transport).payload == b"jobs"
    with pytest.raises(httpx2.HTTPStatusError):
        download_feed("https://busy.example/jobs", None, transport=transport)
    with pytest.raises(HostCooldownError):
        download_feed("https://busy.example/next", None, transport=transport)
    assert requested == ["one.example", "two.example", "one.example", "busy.example"]
    assert clock.sleeps == [3.5]


def test_each_host_keeps_its_own_cadence() -> None:
    clock = FakeClock()
    pacer = _pacer(clock)
    for host in ("a.example", "b.example", "c.example"):
        pacer.wait(f"https://{host}/jobs")
    assert clock.sleeps == []
    pacer.wait("https://A.example/next")
    pacer.wait("https://b.example/next")
    assert clock.sleeps == [3.5]


@pytest.mark.parametrize(
    ("header", "seconds"), [("1200", 1200), ("Thu, 01 Jan 1970 00:20:00 GMT", 1200), ("bad", 30)]
)
def test_retry_after_values(header: str, seconds: int) -> None:
    clock = FakeClock()
    pacer = _pacer(clock)
    pacer.observe("https://busy.example/", 503, header)
    if seconds > pacing.SHORT_PAUSE_SECONDS:
        clock.now += seconds - 61
        with pytest.raises(HostCooldownError, match="HTTP 503"):
            pacer.wait("https://busy.example/next")
        clock.now += 1
    pacer.wait("https://busy.example/next")
    assert clock.now == 1000 + seconds
    pacer.observe("https://busy.example/", 429)
    clock.now += 239
    with pytest.raises(HostCooldownError, match=r"rate limit \(HTTP 429\)"):
        pacer.wait("https://busy.example/next")
    clock.now += 1
    pacer.wait("https://busy.example/next")
    assert clock.now == 1000 + seconds + 300


@pytest.mark.parametrize("scheduled", [False, True])
def test_every_import_is_paced(monkeypatch: MonkeyPatch, scheduled: bool) -> None:
    monkeypatch.delenv("JOB_HOST_CONCURRENCY", raising=False)
    assert not pacing.paced_mode()
    with pacing.import_request_mode(scheduled=scheduled):
        assert pacing.paced_mode()
        assert (os.environ.get("JOB_HOST_CONCURRENCY") == "1") is scheduled
    assert not pacing.paced_mode()
    assert "JOB_HOST_CONCURRENCY" not in os.environ
