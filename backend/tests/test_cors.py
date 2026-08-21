from pathlib import Path

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from job_backend.main import create_app


def test_cors_origins(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("JOB_CORS_ORIGINS", "https://jobs.example, http://127.0.0.1:4200/")
    client = TestClient(create_app(tmp_path / "postgres"))
    for origin in ["https://jobs.example", "http://127.0.0.1:4200"]:
        assert (
            client.get("/health", headers={"Origin": origin}).headers["access-control-allow-origin"]
            == origin
        )
    blocked = client.options(
        "/jobs",
        headers={"Origin": "https://unrelated.example", "Access-Control-Request-Method": "POST"},
    )
    assert blocked.status_code == 400
    assert "access-control-allow-origin" not in blocked.headers
