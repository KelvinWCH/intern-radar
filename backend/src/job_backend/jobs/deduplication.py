import hashlib
import json
from urllib.parse import urlsplit

from pydantic import JsonValue, TypeAdapter

from job_backend.jobs.company_priority import company_key
from job_backend.jobs.employer_ids import employer_job_id
from job_backend.jobs.identity import job_document_id
from job_backend.jobs.models import Job
from job_backend.jobs.urls import canonical_job_url, workday_requisition, workday_tenant
from job_backend.persistence.session import Session
from job_backend.scrape.pipeline.models import ScrapedJob


def job_url_hash(url: str) -> str:
    return hashlib.sha256(canonical_job_url(url).encode()).hexdigest()


_EMPLOYER_PATH_HOSTS = frozenset(
    {
        "job-boards.greenhouse.io",
        "jobs.lever.co",
        "jobs.eu.lever.co",
        "jobs.ashbyhq.com",
        "apply.workable.com",
        "jobs.smartrecruiters.com",
        "careers.smartrecruiters.com",
    }
)


def employer_scope(url: str, company: str) -> list[str]:
    tenant = workday_tenant(url)
    if tenant is not None:
        return ["workday", tenant]
    parts = urlsplit(canonical_job_url(url))
    hostname = parts.hostname or ""
    segments = [segment for segment in parts.path.split("/") if segment]
    if hostname in _EMPLOYER_PATH_HOSTS and segments:
        return [hostname, segments[0].casefold()]
    return [company_key(company), hostname]


def deduplication_key(job: ScrapedJob | Job) -> str | None:
    if job.application_url is None:
        return None
    identifier = employer_job_id(job.source_job_id) or workday_requisition(job.application_url)
    if identifier is None:
        return job_url_hash(job.application_url)
    value = [
        "employer-job-v2",
        *employer_scope(job.application_url, job.company),
        identifier.casefold(),
    ]
    return hashlib.sha256(json.dumps(value).encode()).hexdigest()


def _boards(job: Job) -> list[dict[str, JsonValue]]:
    value = (job.raw_payload or {}).get("job_boards", [])
    boards = TypeAdapter(list[dict[str, JsonValue]]).validate_python(value, strict=True)
    return boards or [
        {"source": job.source, "external_id": job.external_id, "listing_url": job.source_url}
    ]


def _board_union(groups: list[list[dict[str, JsonValue]]]) -> list[dict[str, JsonValue]]:
    distinct = {json.dumps(board, sort_keys=True): board for group in groups for board in group}
    return [distinct[key] for key in sorted(distinct)]


def find_saved_job(session: Session, incoming: ScrapedJob) -> Job | None:
    return session.get(
        Job,
        job_document_id(incoming.source, incoming.external_id, incoming.application_url),
        hydrate=False,
    )


def retain_saved_identity(saved: Job, incoming: ScrapedJob) -> ScrapedJob:
    raw = dict(incoming.raw_payload or {})
    incoming_boards: list[dict[str, JsonValue]] = TypeAdapter(
        list[dict[str, JsonValue]]
    ).validate_python(raw.get("job_boards", []), strict=True)
    if not incoming_boards:
        incoming_boards = [
            {
                "source": incoming.source,
                "external_id": incoming.external_id,
                "listing_url": incoming.source_url,
            }
        ]
    if (
        incoming.source != saved.source
        or "job_boards" in raw
        or "job_boards" in (saved.raw_payload or {})
    ):
        raw["job_boards"] = TypeAdapter(JsonValue).validate_python(
            _board_union([_boards(saved), incoming_boards])
        )
    data = TypeAdapter(dict[str, JsonValue]).validate_python(incoming.model_dump(mode="json"))
    data.update(
        source=saved.source,
        external_id=saved.external_id,
        source_job_id=incoming.source_job_id or saved.source_job_id,
        summary=incoming.summary if incoming.summary is not None else saved.summary,
        raw_description=(
            incoming.raw_description
            if incoming.raw_description is not None
            else saved.raw_description
        ),
        apply_url=incoming.apply_url if incoming.apply_url is not None else saved.apply_url,
        raw_payload=raw,
    )
    return ScrapedJob.model_validate(data, strict=True)
