from fastapi import APIRouter, HTTPException

from job_backend.jobs.user_service import EditConflictError
from job_backend.persistence.database import Database
from job_backend.resumes.profile.models import ResumeProfileEdit, ResumeProfileState
from job_backend.resumes.profile.service import edit_profile, read_profile


def create_router(engine: Database) -> APIRouter:
    router = APIRouter()

    @router.get("/manager", summary="Read source resume and edit revision")
    def get_profile() -> ResumeProfileState:
        return read_profile(engine)

    @router.put("/manager", summary="Save source resume edits without AI")
    def put_profile(edit: ResumeProfileEdit) -> ResumeProfileState:
        try:
            return edit_profile(engine, edit)
        except EditConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None

    return router
