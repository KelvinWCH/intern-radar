from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from job_backend.activity.models import ActivityData, ActivityEvent, ActivityRecord, ActivitySummary
from job_backend.activity.storage import record_activity
from job_backend.jobs.models import JobResponse
from job_backend.main import create_app
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from tests.resumes.helpers import resume


def test_activity_no_duplicates(engine: Database) -> None:
    event = ActivityData(job_id="job-42", company="Example", title="Developer")
    with Session(engine) as connection, connection.begin():
        assert record_activity(
            connection, event_id="job-added:42", kind="job_added", occurred_at=100, data=event
        )
        assert not record_activity(
            connection, event_id="job-added:42", kind="job_added", occurred_at=101, data=event
        )
    with pytest.raises(RuntimeError), Session(engine) as connection, connection.begin():
        record_activity(
            connection, event_id="job-added:43", kind="job_added", occurred_at=102, data=event
        )
        raise RuntimeError("Source action failed")
    with Session(engine) as session:
        saved = session.find(ActivityRecord).all()
        assert len(saved) == 1
        assert saved[0].data == event.model_dump(mode="json")
        assert ActivityEvent.model_validate(saved[0]).occurred_at == 100


def test_activity_routes(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(tmp_path / "postgres")) as client:
        empty = ActivitySummary.model_validate_json(client.get("/activity/summary?days=7").content)
        assert empty.total_applications == 0 and len(empty.days) == 7 and not empty.recent
        payload = {"company": "Example", "title": "Intern", "raw_description": "PRIVATE JOB BODY"}
        created = client.post("/jobs", json=payload)
        job = JobResponse.model_validate_json(created.content)
        assert client.post("/jobs", json=payload).status_code == 200
        edit = {"status": "saved", "notes": "PRIVATE NOTE", "version": 0}
        assert client.put(f"/jobs/{job.id}/user", json=edit).status_code == 200
        assert client.put(f"/jobs/{job.id}/user", json=edit).status_code == 409
        edit["version"] = 1
        assert client.put(f"/jobs/{job.id}/user", json=edit).status_code == 200
        initial = ActivitySummary.model_validate_json(client.get("/activity/summary").content)
        assert len(initial.recent) == 2
        for version, status in [(2, "applied"), (3, "interviewing"), (4, "applied")]:
            assert (
                client.put(
                    f"/jobs/{job.id}/user", json={**edit, "version": version, "status": status}
                ).status_code
                == 200
            )
        summary = ActivitySummary.model_validate_json(client.get("/activity/summary").content)
        assert summary.total_applications == 1
        assert sum(event.kind == "application_marked" for event in summary.recent) == 1
        assert next(stage.count for stage in summary.pipeline if stage.status == "applied") == 1
        assert "PRIVATE" not in summary.model_dump_json()
        source = resume()
        assert (
            client.put(
                "/resumes/manager", json={"resume": source.model_dump(), "revision": 0}
            ).status_code
            == 200
        )
        assert (
            client.put(
                "/resumes/manager", json={"resume": source.model_dump(), "revision": 1}
            ).status_code
            == 200
        )
        source.experience[0].raw_description += " New factual context."
        assert (
            client.put(
                "/resumes/manager", json={"resume": source.model_dump(), "revision": 1}
            ).status_code
            == 409
        )
        assert (
            client.put(
                "/resumes/manager", json={"resume": source.model_dump(), "revision": 2}
            ).status_code
            == 200
        )
        summary = ActivitySummary.model_validate_json(client.get("/activity/summary").content)
        assert sum(event.kind == "resume_updated" for event in summary.recent) == 2
