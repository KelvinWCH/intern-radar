from dataclasses import dataclass, field

from pydantic import JsonValue

from job_backend.jobs.closure import close_job, reopen_job
from job_backend.jobs.identity import job_document_id
from job_backend.jobs.models import ClosedReason, Job
from job_backend.jobs.urls import canonical_job_url
from job_backend.persistence.models import Filter, Junction, ReadQuery
from job_backend.persistence.session import Session
from job_backend.scrape.pipeline.models import JobSource, ScrapeResult

CONFIRM_AFTER_SECONDS = 6 * 3600
_PAGE = 1000


@dataclass(frozen=True)
class ListingSnapshot:
    listed: frozenset[str] | None
    upstream_closed: frozenset[str] = frozenset()
    upstream_open: frozenset[str] = frozenset()
    listed_urls: frozenset[str] = frozenset()


@dataclass
class LivenessOutcome:
    closed: int = 0
    reopened: int = 0
    missing_since: dict[str, int] = field(default_factory=dict[str, int])


def listing_snapshot(source: JobSource, result: ScrapeResult, *, complete: bool) -> ListingSnapshot:
    identities: set[str] = set()
    whole = (
        complete
        and source.complete_listing
        and result.fetched == len(result.documents) + len(result.links) + len(result.listed_urls)
    )
    closed: set[str] = set()
    opened: set[str] = set()
    for document in result.documents:
        if document.external_id is None:
            whole = False
            continue
        identities.add(job_document_id(source.name, document.external_id))
    for link in result.links:
        if link.external_id is None:
            whole = False
            continue
        identity = job_document_id(source.name, link.external_id)
        identities.add(identity)
        status: JsonValue = link.listing_data.get("active")
        if status is False:
            closed.add(identity)
        elif status is True:
            opened.add(identity)
    return ListingSnapshot(
        listed=frozenset(identities) if whole else None,
        upstream_closed=frozenset(closed),
        upstream_open=frozenset(opened - closed),
        listed_urls=frozenset(map(canonical_job_url, result.listed_urls)) if whole else frozenset(),
    )


def saved_statuses(session: Session, source: str) -> dict[str, bool | None]:
    where = Junction((Filter("source", value=source), Filter("deleted_at", "eq")))
    statuses: dict[str, bool | None] = {}
    offset = 0
    while True:
        page = session.select(
            ReadQuery("jobs", where, fields=("id", "active")),
            limit=_PAGE,
            offset=offset,
            count=False,
        )
        for row in page.items:
            identity, active = row.get("id"), row.get("active")
            if isinstance(identity, str):
                statuses[identity] = active if isinstance(active, bool) else None
        if len(page.items) < _PAGE:
            return statuses
        offset += _PAGE


def saved_listed_by_url(session: Session, source: str, listed_urls: frozenset[str]) -> set[str]:
    where = Junction((Filter("source", value=source), Filter("deleted_at", "eq")))
    found: set[str] = set()
    offset = 0
    while True:
        page = session.select(
            ReadQuery("jobs", where, fields=("id", "application_url")),
            limit=_PAGE,
            offset=offset,
            count=False,
        )
        for row in page.items:
            identity, url = row.get("id"), row.get("application_url")
            if isinstance(identity, str) and isinstance(url, str) and url:
                if canonical_job_url(url) in listed_urls:
                    found.add(identity)
        if len(page.items) < _PAGE:
            return found
        offset += _PAGE


def _jobs(session: Session, identities: set[str]) -> list[Job]:
    session.prefetch(Job, identities)
    return [
        job for identity in sorted(identities) if (job := session.get(Job, identity, hydrate=False))
    ]


def reconcile_listing(
    session: Session,
    source: JobSource,
    snapshot: ListingSnapshot,
    previous_missing: dict[str, int],
    now: int,
) -> LivenessOutcome:
    outcome = LivenessOutcome()
    statuses = saved_statuses(session, source.name)
    open_ids = {identity for identity, active in statuses.items() if active is not False}
    closed_ids = set(statuses) - open_ids
    to_close: dict[str, tuple[ClosedReason, str]] = {}
    to_reopen: dict[str, bool | None] = {}
    for identity in snapshot.upstream_closed & open_ids:
        to_close[identity] = ("upstream_closed", "The source list marks this posting closed.")
    for identity in snapshot.upstream_open & closed_ids:
        to_reopen[identity] = True
    listed = snapshot.listed
    if listed is not None:
        if snapshot.listed_urls:
            listed = listed | saved_listed_by_url(session, source.name, snapshot.listed_urls)
        for identity in sorted(open_ids - listed - set(to_close)):
            first_missed = previous_missing.get(identity)
            if first_missed is not None and now - first_missed >= CONFIRM_AFTER_SECONDS:
                to_close[identity] = (
                    "not_listed",
                    "No longer listed on the employer's job board.",
                )
            else:
                outcome.missing_since[identity] = now if first_missed is None else first_missed
        for identity in closed_ids & listed:
            to_reopen.setdefault(identity, None)
    if not to_close and not to_reopen:
        return outcome
    for job in _jobs(session, set(to_close) | set(to_reopen)):
        if job.id in to_close:
            outcome.closed += close_job(job, *to_close[job.id], now)
        elif job.closed_reason in {"not_listed", "upstream_closed"}:
            outcome.reopened += reopen_job(job, now, active=to_reopen[job.id])
    return outcome
