import hashlib
import json
import time
from collections.abc import Callable
from contextlib import closing

from pydantic import JsonValue, TypeAdapter

from job_backend.common.models import AiSettings
from job_backend.jobs.closure import sync_source_status
from job_backend.jobs.deduplication import (
    deduplication_key,
    find_saved_job,
    job_url_hash,
    retain_saved_identity,
)
from job_backend.jobs.descriptions import clean_description
from job_backend.jobs.details import apply_detail_overrides
from job_backend.jobs.identity import job_document_id
from job_backend.jobs.models import Job
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.scrape.models import FailureStage, ScrapeRun, ScrapeTrigger, SourceState
from job_backend.scrape.pipeline.ai import AiNormalizer
from job_backend.scrape.pipeline.flagged_jobs import save_flagged_jobs
from job_backend.scrape.pipeline.heuristics.normalizer import HeuristicNormalizer
from job_backend.scrape.pipeline.job_pages import JobPages
from job_backend.scrape.pipeline.liveness import (
    ListingSnapshot,
    LivenessOutcome,
    listing_snapshot,
    reconcile_listing,
)
from job_backend.scrape.pipeline.models import (
    FetchResult,
    JobNormalizer,
    JobPageSettings,
    JobSource,
    RawDocument,
    ScrapedJob,
    ScrapeResult,
    ScrapeRunResponse,
)
from job_backend.scrape.pipeline.normalization import (
    normalize_snapshot,
    validate_snapshot_documents,
)
from job_backend.scrape.pipeline.targeting import document_is_candidate
from job_backend.scrape.pipeline.telemetry.events import EventRecorder
from job_backend.scrape.pipeline.telemetry.performance import PerformanceTracker, failure_reason
from job_backend.scrape.utils.detail_cache import detail_cache_scope
from job_backend.scrape.utils.hashes import job_content_hash, job_identity_hash
from job_backend.scrape.utils.source_skips import skip_reason, source_unavailable


def apply_source_metadata(saved_job: Job, scraped_job: ScrapedJob) -> None:
    saved_job.is_canada_internship = scraped_job.is_canada_internship
    saved_job.is_toronto_area = scraped_job.is_toronto_area
    saved_job.source = scraped_job.source
    saved_job.external_id = scraped_job.external_id
    saved_job.source_job_id = scraped_job.source_job_id
    saved_job.company = scraped_job.company
    saved_job.title = scraped_job.title
    saved_job.application_url = scraped_job.application_url
    saved_job.apply_url = scraped_job.apply_url
    saved_job.company_url = scraped_job.company_url
    saved_job.locations = scraped_job.locations
    saved_job.category = scraped_job.category
    saved_job.terms = scraped_job.terms
    saved_job.qualifications = TypeAdapter(dict[str, JsonValue]).validate_python(
        scraped_job.qualifications.model_dump(mode="json")
    )
    saved_job.sponsorship = scraped_job.sponsorship
    saved_job.upstream_source = scraped_job.upstream_source
    saved_job.active = scraped_job.active
    saved_job.is_visible = scraped_job.is_visible
    saved_job.date_posted = scraped_job.date_posted
    saved_job.date_updated = scraped_job.date_updated
    saved_job.source_url = scraped_job.source_url
    saved_job.raw_payload = scraped_job.raw_payload
    saved_job.summary = scraped_job.summary
    saved_job.raw_description = scraped_job.raw_description
    saved_job.cleaned_description = clean_description(
        scraped_job.raw_description,
        source_url=scraped_job.source_url or scraped_job.application_url,
    )


def scrape_source(
    engine: Database,
    source: JobSource,
    fetch: Callable[[str | None], FetchResult] | None = None,
    *,
    normalizer: JobNormalizer | None = None,
    page_settings: JobPageSettings | None = None,
    fetch_page: Callable[[str], RawDocument] | None = None,
    task_id: str | None = None,
    trigger: ScrapeTrigger | None = None,
    use_ai: bool = False,
) -> ScrapeRunResponse:
    with Session(engine) as session:
        scrape_run = ScrapeRun(
            source=source.name,
            trigger=trigger,
            status="running",
            started_at=time.time(),
            task_id=task_id,
            phase="discovering",
        )
        session.add(scrape_run)
        session.commit()
        scrape_run_id = scrape_run.id
        source_state = session.get(SourceState, source.name)
        etag = source_state.etag if source_state is not None else None
        previous_extraction_key = source_state.normalizer_key if source_state is not None else None
    performance_tracker = PerformanceTracker()
    performance_tracker.on_event = EventRecorder(engine, scrape_run_id, task_id)
    extractor: JobNormalizer | None = None
    failure_stage: FailureStage = "setup"

    def usage() -> dict[str, int | None]:
        if not isinstance(extractor, AiNormalizer):
            return {"input_tokens": 0, "output_tokens": 0}
        ai_usage_totals = extractor.usage.snapshot()
        return {
            "input_tokens": ai_usage_totals.input_tokens,
            "output_tokens": ai_usage_totals.output_tokens,
        }

    try:
        performance_tracker.event(f"Starting {source.name}")
        extractor = normalizer or (
            AiNormalizer(AiSettings.from_environment()) if use_ai else HeuristicNormalizer()
        )
        performance_tracker.event(
            "AI enrichment enabled"
            if isinstance(extractor, AiNormalizer)
            else "Using local extraction; AI is off"
        )
        job_page_settings = page_settings or JobPageSettings.from_environment()
        if source.page_renderer is not None:
            job_page_settings = job_page_settings.model_copy(
                update={"renderer": source.page_renderer}
            )
        if not source.links_are_apply_urls:
            job_page_settings = job_page_settings.model_copy(update={"include_links": True})
        extraction_settings_key = hashlib.sha256(
            json.dumps(
                [
                    "parallel-shared-pages-v1",
                    "retain-all-extracted-jobs-v1",
                    "canadian-student-discovery-v1",
                    "job-page-security-checks-v2",
                    extractor.cache_key,
                    source.terms,
                    job_page_settings.cache_key,
                    job_page_settings.max_age_days,
                    source.require_recent_dates,
                    source.links_are_apply_urls,
                ]
            ).encode()
        ).hexdigest()
        if previous_extraction_key != extraction_settings_key:
            etag = None
        fetch_source = source.fetch if fetch is None else fetch
        snapshot: ListingSnapshot | None = None
        failure_stage = "discovery"
        performance_tracker.event("Fetching the source listing")
        with performance_tracker.measure("discovery_seconds"):
            with detail_cache_scope(engine):
                fetch_result = fetch_source(etag)
            for failure in fetch_result.failures:
                performance_tracker.record_failure(
                    "discovery",
                    failure.error,
                    failure.url,
                    level="warning" if fetch_result.payload is not None else "error",
                )
            if fetch_result.payload is None and fetch_result.failures:
                raise fetch_result.failures[0].error
            scrape_result = (
                source.scrape(fetch_result.payload) if fetch_result.payload is not None else None
            )
            if scrape_result is not None:
                # grab listing ids before filtering drops anything
                snapshot = listing_snapshot(
                    source, scrape_result, complete=not fetch_result.failures
                )
                candidates = [
                    document
                    for document in validate_snapshot_documents(scrape_result).values()
                    if document_is_candidate(document)
                ]
                excluded = len(scrape_result.documents) - len(candidates)
                if excluded:
                    performance_tracker.event(
                        f"Excluded {excluded:,} unrelated records before extraction; "
                        f"{len(candidates):,} Canadian student candidates remain"
                    )
                scrape_result = ScrapeResult(
                    fetched=scrape_result.fetched, documents=candidates, links=scrape_result.links
                )
        job_pages = JobPages(
            engine,
            job_page_settings,
            fetch_page=fetch_page,
            require_recent_dates=source.require_recent_dates,
            links_are_apply_urls=source.links_are_apply_urls,
            performance=performance_tracker,
        )
        failure_stage = "extraction"
        items_total = (
            len(scrape_result.documents) + len(job_pages.select(scrape_result.links))
            if scrape_result is not None
            else None
        )
        if scrape_result is None:
            performance_tracker.event(
                "Listing is unchanged since the last scrape; nothing new to read"
            )
        else:
            performance_tracker.event(
                f"Listing has {scrape_result.fetched:,} records; {items_total:,} postings to check"
            )
        with Session(engine) as progress_session, progress_session.begin():
            progress_run = progress_session.get(ScrapeRun, scrape_run_id)
            if progress_run is not None:
                progress_run.phase = (
                    "reading and extracting" if scrape_result is not None else "checking cache"
                )
                progress_run.fetched = scrape_result.fetched if scrape_result is not None else 0
                progress_run.items_done = 0 if scrape_result is not None else None
                progress_run.items_total = items_total
        items_done = 0
        last_progress_report_at = 0.0

        def report(processed_documents: int) -> None:
            nonlocal items_done, last_progress_report_at
            items_done = processed_documents
            if time.monotonic() - last_progress_report_at < 5:
                return
            last_progress_report_at = time.monotonic()
            with Session(engine) as report_session, report_session.begin():
                current_run = report_session.get(ScrapeRun, scrape_run_id)
                if current_run is not None:
                    current_run.items_done = (
                        processed_documents + performance_tracker.snapshot().page_failures
                    )
                    for key, value in usage().items():
                        setattr(current_run, key, value)

        scraped_jobs: list[ScrapedJob] = []
        if scrape_result is not None:
            if isinstance(extractor, AiNormalizer):
                extractor.open()
            with closing(job_pages.documents(scrape_result.links)) as documents:
                scraped_jobs = normalize_snapshot(
                    engine,
                    source,
                    scrape_result,
                    extractor,
                    page_documents=documents,
                    max_workers=extractor.settings.concurrency
                    if isinstance(extractor, AiNormalizer)
                    else 1,
                    performance=performance_tracker,
                    on_progress=report,
                )
            with Session(engine) as progress_session, progress_session.begin():
                progress_run = progress_session.get(ScrapeRun, scrape_run_id)
                if progress_run is not None:
                    progress_run.phase = "saving"
                    progress_run.items_done = (
                        items_done + performance_tracker.snapshot().page_failures
                    )
            performance_tracker.event(f"Saving {len(scraped_jobs):,} extracted jobs")
        failure_stage = "persistence"
        liveness = LivenessOutcome()
        with Session(engine) as session, session.begin():
            with performance_tracker.measure("persistence_seconds"):
                scrape_run = session.get(ScrapeRun, scrape_run_id)
                if scrape_run is None:
                    raise RuntimeError("Scrape history record disappeared")
                if scrape_result is None:
                    if etag is None:
                        raise RuntimeError("Received HTTP 304 without an imported snapshot")
                    scrape_run.status = "not_modified"
                else:
                    # skipped postings get read again so dont cache the listing
                    retry_needed = job_pages.retry_needed or performance_tracker.failure_count > 0
                    scrape_run.fetched = scrape_result.fetched
                    scrape_run.matched = sum(
                        scraped_job.is_canada_internship for scraped_job in scraped_jobs
                    )
                    scraped_at = int(time.time())
                    source_state = session.get(SourceState, source.name)
                    previous_missing = (
                        source_state.missing_since if source_state is not None else {}
                    )
                    if snapshot is not None:
                        liveness = reconcile_listing(
                            session, source, snapshot, previous_missing, scraped_at
                        )
                    missing_since = (
                        liveness.missing_since
                        if snapshot is not None and snapshot.listed is not None
                        else previous_missing
                    )
                    session.prefetch(
                        Job,
                        {
                            job_document_id(
                                scraped_job.source,
                                scraped_job.external_id,
                                scraped_job.application_url,
                            )
                            for scraped_job in scraped_jobs
                        },
                    )
                    for scraped_job in scraped_jobs:
                        extraction_fingerprint = scraped_job.extraction_fingerprint
                        saved_job = find_saved_job(session, scraped_job)
                        if saved_job is not None:
                            scraped_job = retain_saved_identity(saved_job, scraped_job)
                            if scraped_job.date_posted is None:
                                scraped_job = scraped_job.model_copy(
                                    update={"date_posted": saved_job.date_posted}
                                )
                            if isinstance(extractor, HeuristicNormalizer):
                                job_fields = scraped_job.model_dump()
                                for name in (
                                    "summary",
                                    "qualifications",
                                    "source_job_id",
                                    "company_url",
                                    "sponsorship",
                                    "upstream_source",
                                    "date_updated",
                                ):
                                    value = getattr(saved_job, name)
                                    if value is not None:
                                        job_fields[name] = value
                                for name in ("active", "is_visible", "date_posted", "category"):
                                    if job_fields[name] is None:
                                        job_fields[name] = getattr(saved_job, name)
                                scraped_job = ScrapedJob.model_validate(job_fields)
                        content_hash = job_content_hash(scraped_job)
                        if saved_job is None:
                            saved_job = Job()
                            apply_source_metadata(saved_job, scraped_job)
                            saved_job.job_hash = job_identity_hash(
                                scraped_job.source, scraped_job.external_id
                            )
                            saved_job.deduplication_key = deduplication_key(scraped_job)
                            saved_job.job_url_hash = job_url_hash(scraped_job.application_url)
                            saved_job.extraction_fingerprint = extraction_fingerprint
                            saved_job.last_changed_at = scraped_at
                            saved_job.first_seen_at = scraped_at
                            saved_job.last_seen_at = scraped_at
                            saved_job.content_hash = content_hash
                            sync_source_status(saved_job, scraped_at)
                            session.add(saved_job)
                            scrape_run.created += 1
                        else:
                            saved_job.last_seen_at = scraped_at
                            saved_job.deduplication_key = deduplication_key(scraped_job)
                            saved_job.job_url_hash = job_url_hash(scraped_job.application_url)
                            saved_job.extraction_fingerprint = extraction_fingerprint
                            if (
                                saved_job.content_hash == content_hash
                                and saved_job.review_reason is None
                            ):
                                scrape_run.unchanged += 1
                            else:
                                apply_source_metadata(saved_job, scraped_job)
                                saved_job.review_reason = None
                                saved_job.details_version += 1
                                saved_job.content_hash = content_hash
                                saved_job.last_changed_at = scraped_at
                                scrape_run.updated += 1
                            apply_detail_overrides(saved_job)
                            sync_source_status(saved_job, scraped_at)
                    save_flagged_jobs(
                        session,
                        source,
                        job_pages.flagged_links,
                        scrape_run,
                        scraped_at,
                        robots_blocked=frozenset(job_pages.robots_blocked),
                    )
                    if source_state is None:
                        session.add(
                            SourceState(
                                source=source.name,
                                etag=None if retry_needed else fetch_result.etag,
                                normalizer_key=extraction_settings_key,
                                missing_since=missing_since,
                            )
                        )
                    else:
                        source_state.etag = None if retry_needed else fetch_result.etag
                        source_state.normalizer_key = extraction_settings_key
                        source_state.missing_since = missing_since
                    scrape_run.status = "completed"
                scrape_run.finished_at = time.time()
                session.flush()
            scrape_run.performance = TypeAdapter(dict[str, JsonValue]).validate_python(
                performance_tracker.snapshot(scrape_run.created).model_dump(mode="json")
            )
            scrape_run.phase = "finished"
            for key, value in usage().items():
                setattr(scrape_run, key, value)
            result = ScrapeRunResponse.model_validate(scrape_run)
        for count, outcome in (
            (liveness.closed, "closed: they left the listing or their source marks them closed"),
            (liveness.reopened, "open again: they are listed once more"),
        ):
            if count:
                performance_tracker.event(
                    f"Marked {count:,} saved posting{'s' if count != 1 else ''} {outcome}"
                )
        performance_tracker.event(
            f"Finished: {result.created} new, {result.updated} updated, "
            f"{result.unchanged} unchanged"
            + (
                f", {performance_tracker.failure_count} skipped"
                if performance_tracker.failure_count
                else ""
            )
        )
        return result
    except Exception as error:
        skipped = source_unavailable(error)
        performance_tracker.record_failure(
            failure_stage, error, level="warning" if skipped else "error", announce=not skipped
        )
        with Session(engine) as session, session.begin():
            failed_run = session.get(ScrapeRun, scrape_run_id)
            if failed_run is not None:
                failed_run.status = "failed"
                failed_run.phase = "skipped" if skipped else "failed"
                failed_run.finished_at = time.time()
                failed_run.error = f"{type(error).__name__}: {failure_reason(error)}"
                failed_run.performance = TypeAdapter(dict[str, JsonValue]).validate_python(
                    performance_tracker.snapshot().model_dump(mode="json")
                )
                for key, value in usage().items():
                    setattr(failed_run, key, value)
        if skipped:
            reason = skip_reason(f"{type(error).__name__}: {failure_reason(error)}")
            performance_tracker.event(
                f"Skipped {source.name} until the next run: {reason}", "warning"
            )
        else:
            performance_tracker.event(
                "Scrape stopped; completed extractions stay cached for the next run", "error"
            )
        raise
    finally:
        if isinstance(extractor, AiNormalizer):
            extractor.close()
