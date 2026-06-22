from pathlib import Path

from fastapi.testclient import TestClient

from job_backend.health.models import HealthResponse
from job_backend.main import create_app


def test_health_endpoint(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "health-state")) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert HealthResponse.model_validate(response.json()).status == "ok"
