import hashlib
import json

from pydantic import HttpUrl, JsonValue, TypeAdapter, ValidationError

from job_backend.jobs.deduplication import deduplication_key, job_url_hash
from job_backend.jobs.identity import job_document_id
from job_backend.jobs.models import Job, ReviewReason
from job_backend.persistence.session import Session
from job_backend.scrape.models import ScrapeRun
from job_backend.scrape.pipeline.heuristics.parsing import location_values, object_value, text_value
from job_backend.scrape.pipeline.models import JobLink, JobSource
from job_backend.scrape.utils.hashes import job_identity_hash
from job_backend.scrape.utils.public_urls import is_linkedin_url


def _url(value: JsonValue) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(TypeAdapter(HttpUrl).validate_python(value))
    except ValidationError:
        return None


def _fill_discovery_details(job: Job, link: JobLink, source: JobSource) -> bool:
    hints = link.listing_data
    company = (
        text_value(hints.get("company_name"))
        or text_value(hints.get("company"))
        or text_value(object_value(hints.get("company")).get("name"))
        or text_value(object_value(hints.get("hiringOrganization")).get("name"))
    )
    title = next(
        (
            value
            for key in ("title", "job_title", "position", "text")
            if (value := text_value(hints.get(key)))
        ),
        None,
    )
    terms = hints.get("terms")
    fields: dict[str, object] = {
        "company": company,
        "title": title,
        "locations": location_values(
            hints.get("locations")
            or hints.get("location")
            or hints.get("jobLocation")
            or object_value(hints.get("categories")).get("location")
        ),
        "terms": [term for term in terms if isinstance(term, str) and term.strip()]
        if isinstance(terms, list)
        else list(source.terms),
        "source_job_id": text_value(hints.get("source_job_id")),
        "company_url": _url(hints.get("company_url")),
        "apply_url": _url(hints.get("apply_url"))
        or (link.url if source.links_are_apply_urls else None),
        "date_posted": link.date_posted,
        "category": text_value(hints.get("category")),
        "sponsorship": text_value(hints.get("sponsorship")),
    }
    changed = False
    for name, value in fields.items():
        current = getattr(job, name)
        if (
            value is not None
            and value != []
            and value != ""
            and (not current or current in ("Not specified", "Posting awaiting review"))
            and name not in (job.detail_overrides or {})
        ):
            setattr(job, name, value)
            changed = True
    return changed


def save_flagged_jobs(
    session: Session,
    source: JobSource,
    links: list[JobLink],
    run: ScrapeRun,
    now: int,
    *,
    robots_blocked: frozenset[str] = frozenset(),
) -> None:
    for link in links:
        reason: ReviewReason = (
            "linkedin_blocked"
            if is_linkedin_url(link.url)
            else "robots_disallowed"
            if link.url in robots_blocked
            else "security_challenge"
        )
        # never opened on purpose, so a job you marked reviewed stays reviewed
        never_opened = reason != "security_challenge"
        external_id = link.external_id or ("url:" + hashlib.sha256(link.url.encode()).hexdigest())
        identity = job_document_id(source.name, external_id, link.url)
        job = session.get(Job, identity, hydrate=False)
        if job is None:
            hints = link.listing_data
            job = Job(
                source=source.name,
                external_id=external_id,
                company="Not specified",
                title="Posting awaiting review",
                application_url=link.url,
                source_url=link.listing_url,
                date_posted=link.date_posted,
                is_visible=True,
                job_hash=job_identity_hash(source.name, external_id),
                job_url_hash=job_url_hash(link.url),
                deduplication_key=job_url_hash(link.url),
                content_hash=hashlib.sha256(
                    json.dumps(["flagged-job-v1", link.model_dump()], sort_keys=True).encode()
                ).hexdigest(),
                raw_payload={"listing_data": hints, "listing_url": link.listing_url},
                first_seen_at=now,
                last_changed_at=now,
            )
            _fill_discovery_details(job, link, source)
            job.deduplication_key = deduplication_key(job)
            job.review_reason = reason
            session.add(job)
            run.created += 1
        else:
            changed = _fill_discovery_details(job, link, source)
            if (job.review_reason is None and not never_opened) or changed:
                job.details_version += 1
                job.last_changed_at = now
                job.deduplication_key = deduplication_key(job)
                run.updated += 1
            else:
                run.unchanged += 1
            if not never_opened or job.review_reason is not None:
                job.review_reason = reason
        job.last_seen_at = now
