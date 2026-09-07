from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.profile.models import UserProfile
from job_backend.resumes.models import ResumeRecord
from job_backend.resumes.profile.models import ResumeProfileEdit, ResumeProfileState
from job_backend.resumes.storage import save_profile


def read_profile(engine: Database) -> ResumeProfileState:
    with Session(engine, read_only=True) as session:
        row = session.get(ResumeRecord, 1)
        return ResumeProfileState.model_validate(
            {
                "resume": UserProfile.model_validate(row.data) if row else None,
                "revision": row.revision if row else 0,
                "updated_at": row.updated_at if row else None,
            }
        )


def edit_profile(engine: Database, edit: ResumeProfileEdit) -> ResumeProfileState:
    return save_profile(engine, edit.resume, expected_revision=edit.revision)
