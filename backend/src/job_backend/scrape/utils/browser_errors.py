from job_backend.scrape.errors import SourceDataError


class BrowserRetryableError(SourceDataError):
    pass


class BrowserAccessError(BrowserRetryableError):
    url: str | None = None


class BrowserUnavailableError(SourceDataError):
    pass
