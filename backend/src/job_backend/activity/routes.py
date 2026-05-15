from typing import Annotated

from fastapi import APIRouter, Query

from job_backend.activity.models import ActivitySummary
from job_backend.activity.service import summarize_activity
from job_backend.persistence.database import Database


def create_router(engine: Database) -> APIRouter:
    router = APIRouter(prefix="/activity", tags=["activity"])

    @router.get("/summary", summary="Read activity and application progress")
    def summary(days: Annotated[int, Query(ge=7, le=90)] = 30) -> ActivitySummary:
        return summarize_activity(engine, days=days)

    return router
