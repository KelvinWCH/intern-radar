import time

from pydantic import JsonValue, TypeAdapter

from job_backend.jobs.deduplication import deduplication_key, job_url_hash
from job_backend.jobs.descriptions import clean_description
from job_backend.jobs.models import Job, JobDetails, JobEdit
from job_backend.jobs.user_service import EditConflictError, JobNotFoundError
from job_backend.persistence.session import Session


def apply_detail_overrides(job: Job) -> None:
    if job.detail_overrides:
        if "active" in job.detail_overrides:
            job.closed_at = job.closed_reason = job.closed_detail = None
        details = JobDetails.model_validate(job.detail_overrides)
        for name, value in details.model_dump(mode="json", exclude_unset=True).items():
            setattr(job, name, value)
        job.job_url_hash = job_url_hash(job.application_url) if job.application_url else None
        job.deduplication_key = deduplication_key(job)
        if (
            "raw_description" in job.detail_overrides
            and "cleaned_description" not in job.detail_overrides
        ):
            job.cleaned_description = clean_description(
                job.raw_description, source_url=job.source_url or job.application_url
            )


def edit_job_details(session: Session, job_id: str, edit: JobEdit) -> Job:
    job = session.get(Job, job_id, hydrate=False)
    if job is None:
        raise JobNotFoundError("Job not found")
    if job.details_version != edit.version:
        raise EditConflictError("Job details changed. Reload the saved job before trying again.")
    changes = TypeAdapter(dict[str, JsonValue]).validate_python(
        edit.model_dump(mode="json", exclude={"version"}, exclude_unset=True)
    )
    if changes:
        job.detail_overrides = {**(job.detail_overrides or {}), **changes}
        apply_detail_overrides(job)
        job.details_version += 1
        job.details_updated_at = int(time.time())
        job.last_changed_at = job.details_updated_at
    session.commit()
    return job
