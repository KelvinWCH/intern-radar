from fastapi import APIRouter

from job_backend.matching.models import MatchStatus
from job_backend.matching.service import match_status
from job_backend.persistence.database import Database


def create_router(engine: Database) -> APIRouter:
    router = APIRouter(tags=["matching"])

    @router.get("/matches/status", summary="Read job matching progress and hardware")
    def status() -> MatchStatus:
        return match_status(engine)

    return router
