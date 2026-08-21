import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlsplit

import httpx2
from pydantic import JsonValue, TypeAdapter

from job_backend.jobs.closure import close_job, reopen_job
from job_backend.jobs.duplicates import job_responses
from job_backend.jobs.models import Job, JobResponse, LinkCheck, LinkStatus
from job_backend.jobs.user_service import JobNotFoundError
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.pipeline.heuristics.markup import PageMarkup
from job_backend.scrape.pipeline.heuristics.structured import structured_record
from job_backend.scrape.pipeline.models import JobPageSettings, RawDocument
from job_backend.scrape.utils.browser_errors import BrowserAccessError
from job_backend.scrape.utils.constants import IMPORTER_USER_AGENT
from job_backend.scrape.utils.job_page_http import HttpPageStatusError, fetch_http_page
from job_backend.scrape.utils.pacing import pace_request, track_response
from job_backend.scrape.utils.page_text import page_text

# phrases sites use when a posting is closed
CLOSED_PHRASES = (
    "no longer accepting applications",
    "job is no longer available",
    "position is no longer available",
    "posting is no longer available",
    "this job is no longer open",
    "position has been filled",
    "this job has expired",
    "this posting has expired",
    "job posting has expired",
    "this job has been closed",
    "this position has been closed",
    "this requisition is no longer",
    "applications are now closed",
    "the job you are looking for is no longer",
    "the job you are looking for doesn't exist",
    "the job you are looking for does not exist",
    "the page you are looking for doesn't exist",
    "the page you are looking for does not exist",
    "job not found",
)
# redirecting here means the posting is gone
ERROR_PATHS = re.compile(r"/(?:errorpage|error)/?$", re.IGNORECASE)
WORKDAY_HOST = re.compile(r"^(?P<tenant>[a-zA-Z0-9-]+)\.wd\d+\.myworkdayjobs\.com$")
WORKDAY_PATH = re.compile(r"^/(?:[a-z]{2}-[A-Z]{2}/)?(?P<site>[A-Za-z0-9_.-]+)/job/(?P<rest>.+)$")


def workday_api_url(url: str) -> str | None:
    parts = urlsplit(url)
    host = WORKDAY_HOST.fullmatch(parts.hostname or "")
    path = WORKDAY_PATH.fullmatch(parts.path)
    if parts.scheme != "https" or host is None or path is None:
        return None
    return (
        f"https://{parts.hostname}/wday/cxs/{host.group('tenant')}/{path.group('site')}"
        f"/job/{path.group('rest')}"
    )


def _expired(value: object, now: int) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.timestamp() < now


def classify_page(document: RawDocument, now: int) -> tuple[LinkStatus, str]:
    parts = urlsplit(document.source_url)
    if ERROR_PATHS.search(parts.path) or ("error", "true") in parse_qsl(parts.query):
        return "closed", "The site redirected to its error page instead of the posting."
    if document.media_type == "application/json":
        if '"jobPostingInfo"' in document.content:
            return "open", "The employer's job board still publishes this posting."
        return "unknown", "The job board answered without posting details."
    markup = PageMarkup(document.content) if "html" in document.media_type else None
    posting = structured_record(document, markup)
    if posting and _expired(posting.get("validThrough"), now):
        return "closed", "The posting's application deadline has passed."
    try:
        text = page_text(document.content, include_structured=False) if markup else ""
    except SourceDataError:
        text = ""
    folded = " ".join(text.casefold().replace("\u2019", "'").split())
    phrase = next((phrase for phrase in CLOSED_PHRASES if phrase in folded), None)
    if phrase is not None:
        return "closed", f'The page says "{phrase}".'
    if posting:
        return "open", "The page still publishes this job posting."
    return "unknown", "The page loaded without a closed notice, but it shows no job posting data."


def check_posting(
    url: str,
    *,
    fetch_page: Callable[[str], RawDocument] | None = None,
    now: int | None = None,
) -> LinkCheck:
    checked_at = int(time.time()) if now is None else now
    target = workday_api_url(url) or url
    settings = JobPageSettings(renderer="http", timeout_seconds=20.0)

    def result(status: LinkStatus, detail: str, final_url: str | None = None) -> LinkCheck:
        return LinkCheck.model_validate(
            {
                "checked_at": checked_at,
                "status": status,
                "detail": detail,
                "url": url,
                "final_url": final_url,
            }
        )

    try:
        if fetch_page is not None:
            document = fetch_page(target)
        else:
            with httpx2.Client(
                event_hooks={"request": [pace_request], "response": [track_response]},
                timeout=httpx2.Timeout(settings.timeout_seconds, connect=10.0),
                follow_redirects=False,
                headers={
                    "User-Agent": IMPORTER_USER_AGENT,
                    "Accept": "text/html,application/json",
                },
            ) as client:
                document = fetch_http_page(target, client=client, settings=settings)
    except HttpPageStatusError as error:
        if error.status in {404, 410}:
            return result("closed", f"The posting page no longer exists (HTTP {error.status}).")
        return result("unknown", f"The site answered HTTP {error.status}; try again later.")
    except BrowserAccessError:
        return result("unknown", "The site asked for a human verification check.")
    except SourceDataError as error:
        return result("unknown", f"The page could not be read: {error}")
    status, detail = classify_page(document, checked_at)
    final_url = document.source_url if document.source_url != target else None
    return result(status, detail, final_url)


def check_saved_job(
    engine: Database,
    job_id: str,
    *,
    fetch_page: Callable[[str], RawDocument] | None = None,
) -> JobResponse:
    with Session(engine) as session:
        job = session.get(Job, job_id, hydrate=False)
        if job is None:
            raise JobNotFoundError("Job not found")
        url = job.application_url or job.apply_url
    if not url:
        raise SourceDataError("Add a posting URL before checking whether it is open.")
    check = check_posting(url, fetch_page=fetch_page)
    with Session(engine) as session, session.begin():
        job = session.get(Job, job_id, hydrate=False)
        if job is None:
            raise JobNotFoundError("Job not found")
        job.link_check = TypeAdapter(dict[str, JsonValue]).validate_python(
            check.model_dump(mode="json")
        )
        if check.status == "closed":
            close_job(job, "link_check", check.detail, check.checked_at)
        elif check.status == "open" and job.closed_reason == "link_check":
            reopen_job(job, check.checked_at)
    with Session(engine) as session:
        job = session.get(Job, job_id, hydrate=False)
        if job is None:
            raise JobNotFoundError("Job not found")
        return job_responses(session, [job])[0]
