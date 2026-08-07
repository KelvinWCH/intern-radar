from job_backend.jobs.models import ClosedReason, Job


def user_set_status(job: Job) -> bool:
    return "active" in (job.detail_overrides or {})


def close_job(job: Job, reason: ClosedReason, detail: str, now: int) -> bool:
    if job.deleted_at is not None or job.active is False or user_set_status(job):
        return False
    job.active = False
    job.closed_at = now
    job.closed_reason = reason
    job.closed_detail = detail
    job.details_version += 1
    job.last_changed_at = now
    return True


def reopen_job(job: Job, now: int, *, active: bool | None = None) -> bool:
    if job.closed_reason is None or user_set_status(job):
        return False
    job.active = active
    clear_closure(job)
    job.details_version += 1
    job.last_changed_at = now
    return True


def clear_closure(job: Job) -> None:
    if job.active is not False:
        job.closed_at = None
        job.closed_reason = None
        job.closed_detail = None


def sync_source_status(job: Job, now: int) -> None:
    if job.active is not False:
        clear_closure(job)
    elif job.closed_reason is None and not user_set_status(job):
        job.closed_at = now
        job.closed_reason = "upstream_closed"
        job.closed_detail = "The source marks this posting closed."
