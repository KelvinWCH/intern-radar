from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.pipeline.telemetry.performance import PerformanceTracker


def test_diagnostics_redacted() -> None:
    metrics = PerformanceTracker()
    error = SourceDataError(
        "HTTP 403 https://user:password@example.com/job?token=private Bearer secret api_key=hidden"
    )
    metrics.record_failure(
        "download", error, "https://user:password@example.com/job?token=private#secret"
    )
    metrics.record_failure("extraction", error)
    for index in range(110):
        metrics.record_failure("download", SourceDataError(f"Failure {index}"))
    result = metrics.snapshot()
    assert (
        result.failure_count == 111
        and len(result.failures) == 100
        and result.failures_omitted == 11
    )
    assert result.failures[0].url == "https://example.com/job"
    for value in ("password", "private", "hidden", "secret"):
        assert value not in result.model_dump_json()
