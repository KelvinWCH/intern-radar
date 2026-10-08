import gzip
from pathlib import Path

from fastapi.testclient import TestClient

from job_backend.jobs.models import Job
from job_backend.main import create_app
from job_backend.persistence.database import make_engine
from job_backend.persistence.session import Session


def test_gzip(tmp_path: Path) -> None:
    state = tmp_path / "postgres"
    app = create_app(state)
    engine = make_engine(state)
    with TestClient(app) as client:
        with Session(engine) as session, session.begin():
            session.add(
                Job(
                    id="large",
                    job_hash="a" * 64,
                    content_hash="b" * 64,
                    raw_description="Complete original description. " * 5000,
                    raw_payload={"original": "Unmodified source payload. " * 5000},
                )
            )
        plain = client.get("/jobs/large", headers={"Accept-Encoding": "identity"})
        assert plain.status_code == 200 and "content-encoding" not in plain.headers
        with client.stream("GET", "/jobs/large", headers={"Accept-Encoding": "gzip"}) as compressed:
            wire = b"".join(compressed.iter_raw())
            assert compressed.headers["content-encoding"] == "gzip"
            assert "accept-encoding" in compressed.headers["vary"].lower()
        assert gzip.decompress(wire) == plain.content
        assert len(wire) < len(plain.content) // 10
        small = client.get("/health", headers={"Accept-Encoding": "gzip"})
        assert small.status_code == 200 and "content-encoding" not in small.headers
    engine.dispose()
