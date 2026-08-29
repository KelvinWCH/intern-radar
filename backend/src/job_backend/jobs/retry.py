import hashlib
import time
from collections.abc import Callable

from filelock import FileLock
from filelock import Timeout as FileLockTimeout

from job_backend.jobs.deduplication import deduplication_key, job_url_hash, retain_saved_identity
from job_backend.jobs.details import apply_detail_overrides
from job_backend.jobs.duplicates import job_responses
from job_backend.jobs.models import Job, JobResponse
from job_backend.jobs.user_service import EditConflictError, JobNotFoundError
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.pipeline.heuristics.normalizer import HeuristicNormalizer
from job_backend.scrape.pipeline.job_pages import JobPages
from job_backend.scrape.pipeline.models import (
    FetchResult,
    JobLink,
    JobPageSettings,
    JobSource,
    RawDocument,
    ScrapedJob,
    ScrapeResult,
)
from job_backend.scrape.pipeline.normalization import normalize_snapshot
from job_backend.scrape.pipeline.pipeline import apply_source_metadata
from job_backend.scrape.utils.hashes import job_content_hash


def _current_job(session: Session, job_id: str, version: int) -> Job:
    job = session.get(Job, job_id, hydrate=False)
    if job is None:
        raise JobNotFoundError("Job not found")
    if job.details_version != version:
        raise EditConflictError("Job changed. Reload before retrying the scrape.")
    if job.review_reason is None:
        raise EditConflictError("This job is no longer flagged. Reload to see its latest details.")
    if job.deleted_at is not None:
        raise EditConflictError("Restore this job before retrying the scrape.")
    return job


def _retry(
    engine: Database,
    job_id: str,
    version: int,
    fetch_page: Callable[[str], RawDocument] | None,
) -> JobResponse:
    with Session(engine) as session:
        original = _current_job(session, job_id, version)
        if not original.application_url:
            raise SourceDataError("Add a posting URL before retrying the scrape.")
        hints = (original.raw_payload or {}).get("listing_data")
        listing_data = dict(hints) if isinstance(hints, dict) else {}
        if original.company not in {"", "Not specified"}:
            listing_data.setdefault("company", original.company)
        if original.title not in {"", "Not specified", "Posting awaiting review"}:
            listing_data.setdefault("title", original.title)
        if original.locations:
            listing_data.setdefault("locations", [location for location in original.locations])
        link = JobLink(
            url=original.application_url,
            listing_url=original.source_url or original.application_url,
            date_posted=original.date_posted,
            external_id=original.external_id,
            listing_data=listing_data,
        )
        source = JobSource(
            name=original.source,
            fetch=lambda _etag: FetchResult(None, None),
            scrape=lambda _payload: ScrapeResult(fetched=1),
            require_recent_dates=False,
            links_are_apply_urls=original.apply_url == original.application_url,
        )

    settings = JobPageSettings.from_environment().model_copy(
        update={
            "cache_seconds": 0,
            "max_downloads_per_scrape": 1,
            "http_concurrency": 1,
            "browser_concurrency": 1,
            "include_links": True,
        }
    )
    pages = JobPages(
        engine,
        settings,
        fetch_page=fetch_page,
        require_recent_dates=False,
        links_are_apply_urls=source.links_are_apply_urls,
    )
    documents = list(pages.documents([link]))
    if not documents:
        if not pages.flagged_links:
            raise SourceDataError(
                "The posting could not be fetched. Its saved details and flag are preserved."
            )
        with Session(engine) as session:
            current = _current_job(session, job_id, version)
            if pages.robots_blocked and current.review_reason != "robots_disallowed":
                current.review_reason = "robots_disallowed"
                current.details_version += 1
                session.commit()
            return job_responses(session, [current])[0]
    extracted = normalize_snapshot(
        engine, source, ScrapeResult(fetched=1, documents=documents), HeuristicNormalizer()
    )
    if len(extracted) != 1:
        raise SourceDataError(
            "Could not identify one job on this page. The posting remains flagged."
        )
    with Session(engine) as session:
        saved = _current_job(session, job_id, version)
        incoming = retain_saved_identity(saved, extracted[0])
        fields = incoming.model_dump()
        for name in (
            "summary",
            "qualifications",
            "source_job_id",
            "company_url",
            "sponsorship",
            "upstream_source",
            "date_updated",
            "active",
            "is_visible",
        ):
            value = getattr(saved, name)
            if value is not None:
                fields[name] = value
        incoming = ScrapedJob.model_validate(fields)
        apply_source_metadata(saved, incoming)
        saved.review_reason = None
        saved.content_hash = job_content_hash(incoming)
        saved.job_url_hash = job_url_hash(incoming.application_url)
        saved.deduplication_key = deduplication_key(incoming)
        saved.extraction_fingerprint = extracted[0].extraction_fingerprint
        saved.last_seen_at = int(time.time())
        saved.last_changed_at = saved.last_seen_at
        saved.details_version += 1
        apply_detail_overrides(saved)
        session.commit()
        return job_responses(session, [saved])[0]


def retry_saved_job(
    engine: Database,
    job_id: str,
    version: int,
    *,
    fetch_page: Callable[[str], RawDocument] | None = None,
) -> JobResponse:
    directory = engine.local_path.parent / "job-retry-locks"
    directory.mkdir(parents=True, exist_ok=True)
    filename = hashlib.sha256(job_id.encode()).hexdigest() + ".lock"
    try:
        with FileLock(directory / filename, timeout=0):
            return _retry(engine, job_id, version, fetch_page)
    except FileLockTimeout:
        raise EditConflictError(
            "A retry is already running for this job. Wait for it to finish."
        ) from None
