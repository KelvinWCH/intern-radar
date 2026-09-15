import math
import os
import random
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import UTC
from email.utils import parsedate_to_datetime
from threading import Lock
from urllib.parse import urlsplit

import httpx2

from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.utils.models import ScrapePacingSettings
from job_backend.scrape.utils.public_urls import is_linkedin_url

SHORT_PAUSE_SECONDS = 60.0
FIRST_THROTTLE_SECONDS = 30.0


class HostCooldownError(SourceDataError):
    pass


class RequestPacer:
    def __init__(
        self,
        settings: ScrapePacingSettings,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self.settings = settings
        self.clock = clock
        self.sleep = sleep
        self.jitter = jitter
        self.wall_clock = wall_clock
        self.lock = Lock()
        self.next_start: dict[str, float] = {}
        self.cooldowns: dict[str, float] = {}
        self.failures: dict[str, int] = {}
        self.reasons: dict[str, str] = {}

    def wait(self, url: str) -> None:
        host = (urlsplit(url).hostname or "").lower()
        while True:
            with self.lock:
                now = self.clock()
                paused_until = self.cooldowns.get(host, 0)
                if paused_until > now:
                    if paused_until - now > SHORT_PAUSE_SECONDS:
                        reason = self.reasons.get(host, "an access block or rate limit")
                        raise HostCooldownError(
                            f"This import paused requests to {host} after {reason}; "
                            "retry on a later run"
                        )
                    wait = paused_until - now
                else:
                    # at least 2-5s between requests to the same site; the spread keeps
                    # parallel workers from lining up on one host
                    wait = self.next_start.get(host, 0.0) - now
                    if wait <= 0:
                        self.next_start[host] = now + self.jitter(
                            self.settings.min_delay_seconds, self.settings.max_delay_seconds
                        )
                        return
            self.sleep(wait)

    def observe(self, url: str, status: int, retry_after: str | None = None) -> None:
        if status not in {401, 403, 429, 503}:
            return
        host = (urlsplit(url).hostname or "").lower()
        with self.lock:
            failures = self.failures.get(host, 0) + 1
            self.failures[host] = failures
            delay = (
                FIRST_THROTTLE_SECONDS
                if failures == 1
                else min(3600.0, 300.0 * 2 ** min(failures - 2, 4))
            )
            self.reasons[host] = (
                f"an access block (HTTP {status})"
                if status in {401, 403}
                else f"a rate limit (HTTP {status})"
                if status == 429
                else f"a service outage (HTTP {status})"
            )
            # a 401/403 means the site doesnt want us, stop for the rest of the run
            if status in {401, 403}:
                delay = math.inf
            elif retry_after:
                try:
                    advertised = float(retry_after)
                except ValueError:
                    try:
                        date = parsedate_to_datetime(retry_after)
                        if date.tzinfo is None:
                            date = date.replace(tzinfo=UTC)
                        advertised = date.timestamp() - self.wall_clock()
                    except (TypeError, ValueError, OverflowError):
                        advertised = 0.0
                if math.isfinite(advertised):
                    delay = max(delay, advertised)
            self.cooldowns[host] = max(self.cooldowns.get(host, 0), self.clock() + delay)


_active_pacer: RequestPacer | None = None


# every import is paced, manual or scheduled; unattended scheduled runs also go slower
@contextmanager
def import_request_mode(*, scheduled: bool) -> Generator[None, None, None]:
    global _active_pacer
    pacer = RequestPacer(ScrapePacingSettings.from_environment())
    overrides = (
        {
            "JOB_HTTP_CONCURRENCY": str(min(2, int(os.environ.get("JOB_HTTP_CONCURRENCY", "6")))),
            "JOB_BROWSER_CONCURRENCY": "1",
            "JOB_HOST_CONCURRENCY": "1",
        }
        if scheduled
        else {}
    )
    previous = {key: os.environ.get(key) for key in overrides}
    previous_pacer = _active_pacer
    _active_pacer = pacer
    os.environ.update(overrides)
    try:
        yield
    finally:
        _active_pacer = previous_pacer
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def paced_mode() -> bool:
    return _active_pacer is not None


def wait_for_request(url: str) -> None:
    if _active_pacer is not None:
        _active_pacer.wait(url)


def observe_response(url: str, status: int, retry_after: str | None = None) -> None:
    if _active_pacer is not None:
        _active_pacer.observe(url, status, retry_after)


def pace_request(request: httpx2.Request) -> None:
    url = str(request.url)
    if is_linkedin_url(url):
        raise SourceDataError("LinkedIn is blocked; its pages are never requested")
    wait_for_request(url)


def track_response(response: httpx2.Response) -> None:
    observe_response(str(response.url), response.status_code, response.headers.get("Retry-After"))
