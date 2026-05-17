import time

from job_backend.activity.models import ActivityData
from job_backend.activity.storage import record_activity
from job_backend.jobs.models import Job, JobUserData, JobUserEdit, JobUserRecord
from job_backend.persistence.database import Database
from job_backend.persistence.errors import ConflictError as EditConflictError
from job_backend.persistence.session import Session


class JobNotFoundError(ValueError):
    pass


def edit_user_data(engine: Database, job_id: str, edit: JobUserEdit) -> JobUserData:
    now = int(time.time())
    with Session(engine) as session, session.begin():
        job = session.get(Job, job_id)
        if job is None:
            raise JobNotFoundError("Job not found")
        previous = JobUserData.model_validate(job.user) if job.user else JobUserData()
        values = edit.model_dump(exclude={"version"})
        if edit.status == "applied" and edit.applied_at is None:
            values["applied_at"] = previous.applied_at if previous.applied_at is not None else now
        values.update(updated_at=now, version=edit.version + 1)
        if previous.version != edit.version:
            raise EditConflictError("Application data changed. Reload before saving your edits.")
        record = session.get(JobUserRecord, job_id)
        if record is None:
            record = JobUserRecord(job_id=job_id)
            session.add(record)
        for key, value in values.items():
            setattr(record, key, value)
        changed = any(
            getattr(previous, key) != value
            for key, value in values.items()
            if key not in {"updated_at", "version"}
        )
        if changed:
            context = ActivityData(
                job_id=job_id,
                company=job.company,
                title=job.title,
                previous_status=previous.status,
                status=edit.status,
            )
            first_application = edit.status == "applied" and record_activity(
                session.connection(),
                event_id=f"application:{job_id}",
                kind="application_marked",
                occurred_at=now,
                data=context,
            )
            if not first_application:
                record_activity(
                    session.connection(),
                    event_id=f"application-edit:{job_id}:{edit.version + 1}",
                    kind="job_saved"
                    if edit.status == "saved" and previous.status != "saved"
                    else "application_updated",
                    occurred_at=now,
                    data=context,
                )
        session.expire_all()
        return JobUserData.model_validate(session.get(JobUserRecord, job_id))
