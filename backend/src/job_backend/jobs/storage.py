import hashlib
import json
import time

from job_backend.activity.models import ActivityData
from job_backend.activity.storage import record_activity
from job_backend.jobs.deduplication import deduplication_key, job_url_hash
from job_backend.jobs.identity import job_document_id, next_manual_url_id
from job_backend.jobs.models import Job, JobCreate, JobResponse, UserSourceType
from job_backend.persistence.errors import ConflictError
from job_backend.persistence.session import Session
from job_backend.scrape.utils.hashes import job_identity_hash


def _target(
    session: Session, external_id: str, application_url: str | None, url_hash: str | None
) -> tuple[str, Job | None]:
    candidate = job_document_id("user", external_id, application_url)
    saved = session.get(Job, candidate, hydrate=False)
    if url_hash is None:
        if saved is not None and (saved.source != "user" or saved.external_id != external_id):
            raise ConflictError("Saved job text identity changed. Reload and retry.")
        return candidate, saved
    if saved is not None and saved.job_url_hash == url_hash:
        return candidate, saved
    matches = session.all(Job, job_url_hash=url_hash)
    if matches:
        saved = min(matches, key=lambda item: (item.first_seen_at, item.id))
        return saved.id, saved
    while saved is not None:
        candidate = next_manual_url_id(candidate)
        saved = session.get(Job, candidate, hydrate=False)
        if saved is not None and saved.job_url_hash == url_hash:
            return candidate, saved
    return candidate, None


def _save_user_job(session: Session, job: JobCreate, source_type: UserSourceType) -> JobResponse:
    identity = json.dumps(
        [
            " ".join(job.company.casefold().split()),
            " ".join(job.title.casefold().split()),
            " ".join(job.raw_description.split()),
        ],
        ensure_ascii=False,
    )
    external_id = hashlib.sha256(identity.encode()).hexdigest()
    url_hash = job_url_hash(job.application_url) if job.application_url else None
    target_id, saved = _target(session, external_id, job.application_url, url_hash)
    if saved is not None:
        session.get(Job, saved.id)
        return JobResponse.model_validate(saved)
    if saved is None:
        now = int(time.time())
        saved = Job(
            id=target_id,
            source="user",
            source_type=source_type,
            external_id=external_id,
            job_hash=job_identity_hash("user", external_id),
            job_url_hash=url_hash,
            deduplication_key=url_hash,
            **job.model_dump(mode="json"),
            is_visible=True,
            content_hash=hashlib.sha256(job.model_dump_json().encode()).hexdigest(),
            first_seen_at=now,
            last_seen_at=now,
            last_changed_at=now,
        )
        saved.deduplication_key = deduplication_key(saved)
        session.add(saved)
        session.flush()
        if source_type == "user_added":
            record_activity(
                session.connection(),
                event_id=f"job-added:{saved.id}",
                kind="job_added",
                occurred_at=now,
                data=ActivityData(job_id=saved.id, company=saved.company, title=saved.title),
            )
    response = JobResponse.model_validate(saved)
    session.commit()
    return response


def save_user_job(session: Session, job: JobCreate, source_type: UserSourceType) -> JobResponse:
    for attempt in range(5):
        try:
            return _save_user_job(session, job, source_type)
        except ConflictError:
            session.rollback()
            if attempt == 4:
                raise
    raise RuntimeError("Save retry loop ended unexpectedly")
