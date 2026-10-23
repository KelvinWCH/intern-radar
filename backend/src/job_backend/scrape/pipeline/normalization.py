import hashlib
import json
import time
from collections import deque
from collections.abc import Callable, Iterable
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from itertools import chain

from pydantic import JsonValue, TypeAdapter

from job_backend.common.logger import get_logger
from job_backend.persistence.database import Database
from job_backend.persistence.errors import DatabaseUnavailableError
from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.pipeline.cache import ScrapeCache
from job_backend.scrape.pipeline.constants import EXTRACTION_CACHE_SECONDS
from job_backend.scrape.pipeline.heuristics.normalizer import HeuristicNormalizer
from job_backend.scrape.pipeline.heuristics.parsing import (
    object_value,
    read_record,
    record_posted_date,
)
from job_backend.scrape.pipeline.models import (
    ExtractionResult,
    JobNormalizer,
    JobSource,
    RawDocument,
    ScrapedJob,
    ScrapeResult,
    SharedExtraction,
)
from job_backend.scrape.pipeline.targeting import document_is_candidate
from job_backend.scrape.pipeline.telemetry.performance import (
    PerformanceTracker,
    failure_reason,
    safe_failure_url,
)

logger = get_logger(__name__)


def _add_original_data_and_links(
    source: JobSource, document: RawDocument, result: ExtractionResult
) -> list[ScrapedJob]:
    if document.external_id is not None and len(result.jobs) > 1:
        raise SourceDataError("A document with a trusted record ID must contain at most one job")
    raw: dict[str, JsonValue] = {
        "content": document.content,
        "media_type": document.media_type,
    }
    if document.media_type == "application/json":
        value = TypeAdapter(JsonValue).validate_json(document.content, strict=True)
        if isinstance(value, dict):
            raw = value
    if document.listing_data:
        raw["listing_data"] = document.listing_data
    jobs: list[ScrapedJob] = []
    posted = document.date_posted
    if posted is None and len(result.jobs) == 1:
        record = read_record(document)
        posted = record_posted_date(object_value(record.get("job")) or record)
    for extracted in result.jobs:
        if (
            document.listing_url is None
            and source.terms
            and not set(source.terms).intersection(extracted.terms)
        ):
            continue
        external_id = document.external_id or (
            "url:" + hashlib.sha256(extracted.application_url.encode()).hexdigest()
        )
        data = TypeAdapter(dict[str, JsonValue]).validate_python(extracted.model_dump(mode="json"))
        data.update(
            source=source.name,
            external_id=external_id,
            source_url=document.source_url,
            raw_description=document.content,
            raw_payload=raw,
        )
        if document.application_url is not None:
            data["application_url"] = document.application_url
        if document.apply_url is not None:
            data["apply_url"] = document.apply_url
        if posted is not None:
            data["date_posted"] = posted
        if document.listing_url is not None:
            raw["job_boards"] = [
                {
                    "source": source.name,
                    "external_id": external_id,
                    "listing_url": document.listing_url,
                }
            ]
        jobs.append(ScrapedJob.model_validate(data, strict=True))
    return jobs


def validate_snapshot_documents(scraped: ScrapeResult) -> dict[str, RawDocument]:
    if scraped.fetched < len(scraped.documents) or scraped.fetched < 0:
        raise SourceDataError("Scraper reported an invalid upstream record count")
    documents: dict[str, RawDocument] = {}
    identities: dict[str, str] = {}
    for document in scraped.documents:
        encoded = json.dumps(document.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
        if document.external_id is not None:
            previous = identities.get(document.external_id)
            if previous is not None and previous != fingerprint:
                raise SourceDataError("Scraper returned conflicting duplicate record IDs")
            identities[document.external_id] = fingerprint
        documents[fingerprint] = document
    return documents


def normalize_snapshot(
    engine: Database,
    source: JobSource,
    scraped: ScrapeResult,
    normalizer: JobNormalizer,
    *,
    page_documents: Iterable[RawDocument] = (),
    max_workers: int = 1,
    performance: PerformanceTracker | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> list[ScrapedJob]:
    documents = validate_snapshot_documents(scraped)
    jobs: dict[str, ScrapedJob] = {}
    calls = 0
    uses_ai = not isinstance(normalizer, HeuristicNormalizer)
    cache_key = normalizer.cache_key
    cache = ScrapeCache(engine)
    metrics = performance or PerformanceTracker()
    seen: set[str] = set()
    in_flight: dict[str, Future[ExtractionResult]] = {}
    pending: deque[tuple[RawDocument, str, Future[ExtractionResult]]] = deque()
    stored: set[str] = set()
    done = 0
    skipped = 0
    succeeded = 0
    first_error: Exception | None = None

    def advance() -> None:
        nonlocal done
        done += 1
        if on_progress is not None:
            on_progress(done)

    def extract(document: RawDocument) -> ExtractionResult:
        if uses_ai:
            metrics.increment("ai_calls")
        try:
            if not uses_ai:
                return normalizer.extract(document)
            with metrics.measure("ai_seconds"):
                result = normalizer.extract(document)
                return ExtractionResult.model_validate_json(result.model_dump_json(), strict=True)
        except Exception:
            if uses_ai:
                metrics.increment("ai_failures")
            raise

    def finish() -> None:
        nonlocal skipped, succeeded, first_error
        document, fingerprint, future = pending.popleft()
        try:
            result = future.result()
            normalized = _add_original_data_and_links(source, document, result)
        except (CancelledError, DatabaseUnavailableError):
            raise
        except Exception as error:
            metrics.record_failure("extraction", error, document.source_url, level="warning")
            metrics.event(f"Skipping {document.source_url}; continuing with the rest", "warning")
            logger.warning(
                "Could not extract application page %s: %s: %s; continuing",
                safe_failure_url(document.source_url),
                type(error).__name__,
                failure_reason(error),
            )
            skipped += 1
            first_error = first_error or error
            advance()
            return
        if fingerprint not in stored:
            cache.put(
                SharedExtraction(
                    fingerprint=fingerprint,
                    normalizer_key=cache_key,
                    result=TypeAdapter(dict[str, JsonValue]).validate_python(
                        result.model_dump(mode="json")
                    ),
                    source=source.name,
                    created_at=int(time.time()),
                ),
                ttl_seconds=EXTRACTION_CACHE_SECONDS,
            )
            stored.add(fingerprint)
        for job in normalized:
            # a page with many jobs shares one model response, not one job id
            job.extraction_fingerprint = fingerprint if len(result.jobs) == 1 else None
            previous_job = jobs.get(job.external_id)
            if previous_job is not None and previous_job != job:
                raise SourceDataError("Normalizer returned conflicting duplicate job identities")
            jobs[job.external_id] = job
        succeeded += 1
        found = len(normalized)
        metrics.event(
            f"Extracted {found} job{'s' if found != 1 else ''} from {document.source_url}"
            if found
            else f"No matching job on {document.source_url}"
        )
        advance()

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="scrape-ai") as executor:
        try:
            for document in chain(documents.values(), page_documents):
                if not document_is_candidate(document):
                    metrics.event(f"Skipping unrelated posting {document.source_url}")
                    advance()
                    continue
                encoded = json.dumps(
                    document.model_dump(mode="json"), sort_keys=True, ensure_ascii=False
                )
                original_hash = hashlib.sha256(encoded.encode()).hexdigest()
                if original_hash in seen:
                    advance()
                    continue
                seen.add(original_hash)
                metrics.increment("documents")
                input_document = document.model_copy(
                    update={"external_id": None, "listing_url": None}
                )
                encoded_input = json.dumps(
                    [
                        "shared-extraction-v1",
                        cache_key,
                        input_document.model_dump(mode="json"),
                        document.external_id is not None,
                    ],
                    sort_keys=True,
                    ensure_ascii=False,
                )
                fingerprint = hashlib.sha256(encoded_input.encode()).hexdigest()
                future = in_flight.get(fingerprint)
                if future is not None:
                    if uses_ai:
                        metrics.increment("ai_cache_hits")
                else:
                    cached = cache.get(
                        SharedExtraction,
                        (fingerprint, cache_key),
                        ttl_seconds=EXTRACTION_CACHE_SECONDS,
                    )
                    result = (
                        ExtractionResult.model_validate(cached.result)
                        if cached is not None
                        else None
                    )
                    shared = cached is not None and cached.source != source.name
                    if result is not None:
                        metrics.event(f"Reusing saved extraction for {document.source_url}")
                        future = Future[ExtractionResult]()
                        future.set_result(result)
                        if uses_ai:
                            metrics.increment("ai_cache_hits")
                        if shared and uses_ai:
                            metrics.increment("shared_cache_hits")
                        stored.add(fingerprint)
                    else:
                        if calls >= normalizer.max_calls_per_scrape:
                            raise SourceDataError(
                                "AI call limit reached; extractions were cached. "
                                "Rerun to resume or increase "
                                "JOB_AI_MAX_CALLS_PER_IMPORT"
                            )
                        calls += 1
                        metrics.event(
                            (
                                f"Sending {document.source_url} to AI "
                                if uses_ai
                                else f"Reading basic facts from {document.source_url} "
                            )
                            + f"({len(document.content):,} characters)"
                        )
                        future = executor.submit(extract, input_document)
                    in_flight[fingerprint] = future
                pending.append((document, fingerprint, future))
                if len(pending) >= max_workers * 2:
                    finish()
            while pending:
                finish()
        except BaseException:
            while pending:
                try:
                    finish()
                except Exception:
                    pass
            raise
    if first_error is not None and not succeeded:
        raise first_error
    return list(jobs.values())
