import re
from collections.abc import Callable, Generator
from contextlib import contextmanager
from threading import Lock
from time import perf_counter
from urllib.parse import urlsplit, urlunsplit

from pydantic import ValidationError

from job_backend.scrape.models import FailureStage, ScrapeFailure, ScrapePerformance
from job_backend.scrape.pipeline.telemetry.models import (
    PerformanceCounter,
    PerformanceTiming,
    ScrapeEventLevel,
)


def safe_failure_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or parts.hostname is None:
            return "[invalid URL]"
        return urlunsplit((parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path, "", ""))
    except ValueError:
        return "[invalid URL]"


def failure_reason(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "; ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in error.errors(include_input=False, include_context=False, include_url=False)
        )[:1000]
    reason = re.sub(r"https?://[^\s<>\"']+", lambda match: safe_failure_url(match[0]), str(error))
    reason = re.sub(r"(?i)\bBearer\s+\S+", "Bearer [redacted]", reason)
    reason = re.sub(
        r"(?i)\b(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*[^\s,;]+",
        r"\1=[redacted]",
        reason,
    )
    return reason[:1000] or type(error).__name__


class PerformanceTracker:
    def __init__(self) -> None:
        self.started = perf_counter()
        self.lock = Lock()
        self.values: dict[str, float | int] = {}
        self.failures: list[ScrapeFailure] = []
        self.recorded_errors: list[Exception] = []
        self.failure_count = 0
        self.on_event: Callable[[str, ScrapeEventLevel], None] | None = None

    def event(self, message: str, level: ScrapeEventLevel = "info") -> None:
        sink = self.on_event
        if sink is None:
            return
        try:
            sink(failure_reason(Exception(message)), level)
        except Exception:
            return

    def record_failure(
        self,
        stage: FailureStage,
        error: Exception,
        url: str | None = None,
        *,
        level: ScrapeEventLevel = "error",
        announce: bool = True,
    ) -> None:
        with self.lock:
            if any(previous is error for previous in self.recorded_errors):
                return
            self.failure_count += 1
            if len(self.failures) < 100:
                self.recorded_errors.append(error)
                self.failures.append(
                    ScrapeFailure(
                        stage=stage,
                        error_type=type(error).__name__,
                        reason=failure_reason(error),
                        url=safe_failure_url(url) if url else None,
                    )
                )
        if not announce:
            return
        where = f" for {safe_failure_url(url)}" if url else ""
        self.event(f"{stage.capitalize()} failed{where}: {failure_reason(error)}", level)

    def increment(self, key: PerformanceCounter) -> None:
        with self.lock:
            self.values[key] = self.values.get(key, 0) + 1

    @contextmanager
    def measure(self, key: PerformanceTiming) -> Generator[None, None, None]:
        started = perf_counter()
        try:
            yield
        finally:
            with self.lock:
                self.values[key] = self.values.get(key, 0) + perf_counter() - started

    def snapshot(self, created: int = 0) -> ScrapePerformance:
        elapsed = perf_counter() - self.started
        with self.lock:
            values = dict(self.values)
            failures = list(self.failures)
            failure_count = self.failure_count
        return ScrapePerformance.model_validate(
            {
                **values,
                "elapsed_seconds": elapsed,
                "jobs_per_minute": created * 60 / elapsed if elapsed else 0,
                "failures": failures,
                "failure_count": failure_count,
                "failures_omitted": failure_count - len(failures),
            }
        )
