import time

from pydantic import JsonValue, TypeAdapter

from job_backend.activity.models import ActivityData
from job_backend.activity.storage import record_activity
from job_backend.jobs.user_service import EditConflictError
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.profile.models import UserProfile
from job_backend.resumes.models import ResumeRecord, UserResume
from job_backend.resumes.profile.models import ResumeProfileState


class ResumeNotFoundError(ValueError):
    pass


def load_resume(engine: Database) -> UserResume:
    with Session(engine, read_only=True) as session:
        record = session.get(ResumeRecord, 1)
        if record is None:
            raise ResumeNotFoundError("Upload or save a user resume before tailoring")
        return UserProfile.model_validate(record.data)


def save_resume(
    engine: Database, resume: UserResume, *, expected_revision: int | None = None
) -> UserResume:
    save_profile(engine, resume, expected_revision=expected_revision)
    return resume


def save_profile(
    engine: Database, resume: UserResume, *, expected_revision: int | None = None
) -> ResumeProfileState:
    now = int(time.time())
    with Session(engine) as session, session.begin():
        record = session.get(ResumeRecord, 1)
        revision = record.revision if record else 0
        previous = record.data if record else None
        if expected_revision is not None and expected_revision != revision:
            raise EditConflictError("Source resume changed. Reload before saving your edits.")
        if not isinstance(resume, UserProfile):
            existing = UserProfile.model_validate(previous) if previous else None
            merged = {
                **(existing.model_dump(mode="json") if existing else {}),
                **resume.model_dump(mode="json"),
            }
            resume = UserProfile.model_validate(merged)
            if existing:
                for entry in resume.experience:
                    match = next(
                        (
                            item
                            for item in existing.experience
                            if (item.company, item.title, item.start_date)
                            == (entry.company, entry.title, entry.start_date)
                        ),
                        None,
                    )
                    if match and not any(entry.context.model_dump().values()):
                        entry.context = match.context
                for project in resume.projects:
                    match_project = next(
                        (
                            item
                            for item in existing.projects
                            if (item.name, item.start_date) == (project.name, project.start_date)
                        ),
                        None,
                    )
                    if match_project and not any(project.context.model_dump().values()):
                        project.context = match_project.context
        data = TypeAdapter(dict[str, JsonValue]).validate_python(resume.model_dump(mode="json"))
        session.merge(ResumeRecord(id=1, data=data, updated_at=now, revision=revision + 1))
        if previous != data:
            record_activity(
                session,
                event_id=f"resume:{revision + 1}",
                kind="resume_updated",
                occurred_at=now,
                data=ActivityData(profile_revision=revision + 1),
            )
    return ResumeProfileState(resume=resume, revision=revision + 1, updated_at=now)
