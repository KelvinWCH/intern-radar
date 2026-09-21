import json
import re

import httpx2
from playwright.sync_api import Error as PlaywrightError

from job_backend.common.discord import error_summary
from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.utils.browser_errors import BrowserUnavailableError

SKIPPED_PHASES = frozenset({"skipped", "timeout"})
_HTTP_STATUS = re.compile(
    r"(?:client error|server error|redirect response) '(\d{3})", re.IGNORECASE
)
_HTTP_HINTS = {
    "401": "it requires sign-in",
    "403": "it may be blocking automated requests",
    "404": "the listing was not found",
    "429": "it is rate limiting requests",
}


def source_unavailable(error: BaseException) -> bool:
    current: BaseException | None = error
    for _ in range(5):
        if current is None:
            return False
        if isinstance(current, BrowserUnavailableError):
            return False
        if isinstance(
            current,
            SourceDataError
            | httpx2.HTTPError
            | TimeoutError
            | ConnectionError
            | json.JSONDecodeError
            | PlaywrightError,
        ):
            return True
        current = current.__cause__
    return False


def skip_reason(detail: str) -> str:
    status = _HTTP_STATUS.search(detail)
    if status is not None:
        code = status.group(1)
        hint = _HTTP_HINTS.get(code, "it is unavailable" if code >= "500" else "")
        return f"The site answered HTTP {code}" + (f"; {hint}." if hint else ".")
    if "JSONDecodeError" in detail:
        return "The site returned a page instead of the expected data."
    return re.sub(r"(?i)\berror\b", "problem", error_summary(detail))
