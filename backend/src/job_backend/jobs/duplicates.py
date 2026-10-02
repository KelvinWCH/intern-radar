from collections import defaultdict
from collections.abc import Sequence

from pydantic import JsonValue, TypeAdapter

from job_backend.jobs.document_response import document_summaries
from job_backend.jobs.employer_ids import employer_job_id
from job_backend.jobs.models import (
    DuplicatedJob,
    DuplicatedJobs,
    Job,
    JobResponse,
    JobUserRecord,
    MatchReason,
)
from job_backend.matching.views import match_views
from job_backend.persistence.models import Document, Filter, Junction, Order, ReadQuery
from job_backend.persistence.session import Session

_FIELDS = (
    "id",
    "source",
    "external_id",
    "company",
    "title",
    "source_job_id",
    "application_url",
    "source_url",
    "first_seen_at",
    "date_posted",
    "deleted_at",
    "extraction_fingerprint",
    "job_url_hash",
    "deduplication_key",
)
_IDENTITIES = ("extraction_fingerprint", "job_url_hash", "deduplication_key")
_DOCUMENT = TypeAdapter(Document)


def _metadata(job: Job) -> Document:
    row = _DOCUMENT.validate_python({field: getattr(job, field) for field in _FIELDS})
    row["raw_payload.job_boards"] = (job.raw_payload or {}).get("job_boards")
    return row


def _keys(row: Document) -> list[tuple[str, str]]:
    identifier = row.get("source_job_id")
    valid_id = employer_job_id(identifier if isinstance(identifier, str) else None)
    return [
        (field, value)
        for field in _IDENTITIES
        if field != "deduplication_key" or identifier is None or valid_id is not None
        if isinstance(value := row.get(field), str) and value
    ]


def _reason(job: Job, other: Document) -> MatchReason:
    if job.extraction_fingerprint and job.extraction_fingerprint == other.get(
        "extraction_fingerprint"
    ):
        return "identical_extraction_input"
    if job.job_url_hash and job.job_url_hash == other.get("job_url_hash"):
        identifier = other.get("source_job_id")
        first = employer_job_id(job.source_job_id)
        second = employer_job_id(identifier if isinstance(identifier, str) else None)
        if first and second and first != second:
            return "conflicting_employer_ids"
        return "same_url"
    return "same_employer_id"


def _listing_url(boards: JsonValue, source: JsonValue) -> str | None:
    if isinstance(boards, list):
        for board in boards:
            if isinstance(board, dict) and board.get("source") == source:
                url = board.get("listing_url")
                if isinstance(url, str):
                    return url
    return None


def _candidates(session: Session, targets: list[Document]) -> list[Document]:
    keys = {key for row in targets for key in _keys(row)}
    if not keys:
        return []
    members: dict[str, list[JsonValue]] = {}
    for field, value in sorted(keys):
        members.setdefault(field, []).append(value)
    query = ReadQuery(
        "jobs",
        Junction(
            (
                Filter("deleted_at"),
                Junction(
                    tuple(Filter(field, "in", values) for field, values in members.items()),
                    "or",
                ),
            )
        ),
        (Order("@key"),),
        fields=(*_FIELDS, "raw_payload.job_boards"),
        source=True,
    )
    rows: dict[str, Document] = {}
    position = 0
    while True:
        page = session.select(query, limit=1000, offset=position, count=False).items
        rows.update((str(row["id"]), row) for row in page)
        if len(page) < 1000:
            break
        position += len(page)
    for key, record in session.records.items():
        if isinstance(record, Job):
            if key in session.deleted:
                rows.pop(record.id, None)
            else:
                rows[record.id] = _metadata(record)
    return [row for row in rows.values() if row.get("deleted_at") is None]


def job_responses(session: Session, jobs: Sequence[Job]) -> list[JobResponse]:
    if not jobs:
        return []
    if session.read_only:
        users = {
            user.job_id: user
            for user in session.match_any(JobUserRecord, "job_id", {job.id for job in jobs})
        }
        documents = document_summaries(session, set(users))
        for job in jobs:
            job.user = users.get(job.id)
            if job.user is not None:
                job.user.documents = documents.get(job.id, [])
    targets = [_metadata(job) for job in jobs]
    groups: dict[tuple[str, str], dict[str, Document]] = defaultdict(dict)
    for candidate in _candidates(session, targets):
        for key in _keys(candidate):
            groups[key][str(candidate["id"])] = candidate
    matches = match_views(session, [job.id for job in jobs])
    responses: list[JobResponse] = []
    for job, target in zip(jobs, targets, strict=True):
        if not session.read_only:
            session.get(Job, job.id)
        related: dict[str, Document] = {}
        for key in _keys(target):
            related.update(groups[key])
        related.pop(job.id, None)
        duplicates = [
            DuplicatedJob.model_validate(
                {
                    **{
                        field: other[field]
                        for field in DuplicatedJob.model_fields
                        if field in other
                    },
                    "source_job_id": employer_job_id(
                        value if isinstance(value := other.get("source_job_id"), str) else None
                    ),
                    "listing_url": _listing_url(
                        other.get("raw_payload.job_boards"), other.get("source")
                    ),
                    "raw_description": None,
                    "match_reason": _reason(job, other),
                }
            )
            for other in sorted(related.values(), key=lambda item: str(item["id"]))
        ]
        response = JobResponse.model_validate(job)
        for document in response.user.documents:
            document.date_posted = job.date_posted
        response.duplicated_jobs = DuplicatedJobs(items=duplicates)
        response.match = matches.get(job.id)
        responses.append(response)
    return responses
