from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from job_backend.jobs.details import edit_job_details
from job_backend.jobs.models import Job, JobCreate, JobEdit, JobResponse
from job_backend.jobs.storage import save_user_job
from job_backend.jobs.user_service import EditConflictError
from job_backend.main import create_app
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from tests.helpers import qualifications


def test_manual_job_saved(tmp_path: Path) -> None:
    path = tmp_path / "postgres"
    entry = JobCreate(
        company="Example",
        title="Developer",
        raw_description="Full description",
        locations=["Toronto", "Remote"],
        terms=["Summer 2027"],
        category="Engineering",
        application_url="https://example.com/jobs/1",
        apply_url="https://example.com/apply/1",
        company_url="https://example.com",
        sponsorship="Available",
        date_posted=100,
        source_job_id="REQ-1",
        summary="Original summary",
        qualifications=qualifications(),
    )
    with TestClient(create_app(path)) as client:
        response = client.post("/jobs", json=entry.model_dump(mode="json"))
        assert response.status_code == 200
        original = JobResponse.model_validate_json(response.content)
        assert original.locations == ["Toronto", "Remote"] and original.date_posted == 100
        response = client.patch(
            f"/jobs/{original.id}",
            json={
                "version": original.details_version,
                "title": "Corrected",
                "application_url": None,
                "locations": [],
                "qualifications": None,
                "active": False,
            },
        )
        assert response.status_code == 200
        saved = JobResponse.model_validate_json(response.content)
        assert saved.title == "Corrected" and saved.company == original.company
        assert saved.locations == [] and saved.qualifications is None and saved.active is False
        assert saved.application_url is None and saved.apply_url == original.apply_url
        assert saved.details_version == 1 and saved.details_updated_at is not None
        assert saved.source_type == original.source_type and saved.job_hash == original.job_hash
        assert (
            saved.content_hash == original.content_hash
            and saved.first_seen_at == original.first_seen_at
        )
        assert (
            client.patch(f"/jobs/{saved.id}", json={"version": 0, "title": "Stale"}).status_code
            == 409
        )
    with TestClient(create_app(path)) as client:
        assert JobResponse.model_validate_json(client.get(f"/jobs/{saved.id}").content) == saved
        assert (
            client.patch("/jobs/99999", json={"version": 0, "title": "Missing"}).status_code == 404
        )


def test_concurrent_edits(engine: Database) -> None:
    with Session(engine) as session:
        created = save_user_job(session, JobCreate(raw_description="Description"), "user_added")

    def edit(index: int) -> bool:
        with Session(engine) as session:
            try:
                edit_job_details(session, created.id, JobEdit(version=0, title=f"Title {index}"))
                return True
            except EditConflictError:
                return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(edit, range(2))) == [False, True]
    with Session(engine) as session:
        saved = session.find(Job).first()
        assert saved is not None and saved.details_version == 1
