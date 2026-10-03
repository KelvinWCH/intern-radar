from fastapi import APIRouter, HTTPException

from job_backend.jobs.user_service import EditConflictError
from job_backend.persistence.database import Database
from job_backend.profile.models import UserProfileEdit, UserProfileState
from job_backend.profile.service import edit_user_profile, read_user_profile


def create_router(engine: Database) -> APIRouter:
    router = APIRouter(tags=["profile"])

    @router.get("/profile", summary="Read your complete candidate profile")
    def get_profile() -> UserProfileState:
        return read_user_profile(engine)

    @router.put("/profile", summary="Save your complete candidate profile")
    def put_profile(edit: UserProfileEdit) -> UserProfileState:
        try:
            return edit_user_profile(engine, edit)
        except EditConflictError as error:
            raise HTTPException(409, str(error)) from None

    return router
