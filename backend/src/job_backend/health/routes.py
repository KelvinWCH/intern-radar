from fastapi import APIRouter

from job_backend.health.models import HealthResponse

router = APIRouter()


@router.get("/health", summary="Check API availability")
def health() -> HealthResponse:
    return HealthResponse(status="ok")
