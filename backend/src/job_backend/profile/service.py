from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.profile.models import UserProfile, UserProfileEdit, UserProfileState
from job_backend.resumes.models import ResumeRecord
from job_backend.resumes.storage import save_profile


def read_user_profile(engine: Database) -> UserProfileState:
    with Session(engine) as session:
        record = session.get(ResumeRecord, 1)
        return UserProfileState(
            profile=UserProfile.model_validate(record.data) if record else None,
            revision=record.revision if record else 0,
            updated_at=record.updated_at if record else None,
        )


def edit_user_profile(engine: Database, edit: UserProfileEdit) -> UserProfileState:
    saved = save_profile(engine, edit.profile, expected_revision=edit.revision)
    return UserProfileState(
        profile=edit.profile, revision=saved.revision, updated_at=saved.updated_at
    )
