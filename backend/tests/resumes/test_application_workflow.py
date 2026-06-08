from pathlib import Path
from uuid import uuid4

import httpx2
from fastapi.testclient import TestClient

from job_backend.jobs.models import DocumentDetail, Job, JobDocument, JobResponse
from job_backend.main import create_app
from job_backend.persistence.database import make_engine
from job_backend.persistence.session import Session
from job_backend.resumes.dependencies import resume_ai_settings
from job_backend.resumes.profile.models import ResumeProfileState
from tests.resumes.helpers import completion, resume, selection, settings, workflow_response
from tests.resumes.test_cover_letter import letter_content


def test_tailoring_marks_applied(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        research = workflow_response(request)
        if research is not None:
            return research
        assert "PRIVATE APPLICATION NOTE" not in request.content.decode()
        calls += 1
        return completion(
            (
                selection() if b"tailored_resume_content" in request.content else letter_content()
            ).model_dump_json()
        )

    database = tmp_path / "postgres"
    app = create_app(database, resume_transport=httpx2.MockTransport(handler))
    app.dependency_overrides[resume_ai_settings] = settings
    engine = make_engine(database)
    try:
        with TestClient(app) as client:
            profile = client.put(
                "/resumes/manager", json={"resume": resume().model_dump(), "revision": 0}
            )
            assert profile.status_code == 200
            job = JobResponse.model_validate_json(
                client.post(
                    "/jobs/for-tailoring",
                    json={
                        "company": "Target Employer",
                        "title": "Backend Intern",
                        "raw_description": (
                            "Build Python APIs, use Redis, and benchmark search performance."
                        ),
                    },
                ).content
            )
            assert job.source_type == "user_auto_add" and job.user.status == "new"
            edit = {
                "status": "saved",
                "notes": "PRIVATE APPLICATION NOTE",
                "version": 0,
                "follow_up_at": 1800000000,
                "applied_at": None,
            }
            saved = client.put(f"/jobs/{job.id}/user", json=edit)
            assert saved.status_code == 200
            body = {
                "request_id": str(uuid4()),
                "include_resume": True,
                "include_cover_letter": True,
            }
            generated = client.post(f"/jobs/{job.id}/tailor", json=body)
            assert generated.status_code == 200, generated.text
            documents = DocumentDetail.model_validate_json(generated.content)
            assert documents.resume is not None and documents.cover_letter is not None
            assert documents.status == "completed" and documents.profile_revision == 1
            state = JobResponse.model_validate_json(client.get(f"/jobs/{job.id}").content).user
            assert state.status == "saved" and state.applied_at is None
            assert state.notes == edit["notes"] and state.follow_up_at == edit["follow_up_at"]
            assert len(state.documents) == 1
            replay = client.post(f"/jobs/{job.id}/tailor", json=body)
            assert replay.content == generated.content and calls == 2
            assert client.put(f"/jobs/{job.id}/user", json=edit).status_code == 409
            source_edit = resume()
            source_edit.name = "Updated Source"
            assert (
                client.put(
                    "/resumes/manager", json={"resume": source_edit.model_dump(), "revision": 1}
                ).status_code
                == 200
            )
            with Session(engine) as session, session.begin():
                saved_job = session.get(Job, job.id)
                assert saved_job is not None
                saved_job.raw_description = "New scraped description"
            unchanged = client.get(f"/documents/{documents.id}")
            assert unchanged.content == generated.content
            assert "benchmark search" in documents.job_description
            for kind, stem in [
                ("resume", "Target_Employer_Alex_Example"),
                ("cover-letter", "Target_Employer_Alex_Example_Cover_Letter"),
            ]:
                pdf = client.get(f"/documents/{documents.id}/{kind}/pdf")
                assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
                assert pdf.headers["cache-control"] == "private, no-store"
                assert pdf.headers["content-disposition"] == f'attachment; filename="{stem}.pdf"'
                tex = client.get(f"/documents/{documents.id}/{kind}/tex")
                assert tex.status_code == 200 and "documentclass" in tex.text
                assert tex.headers["content-disposition"] == f'attachment; filename="{stem}.tex"'
            assert calls == 2
            with Session(engine) as session:
                row = session.find(JobDocument).first()
                assert (
                    row is not None
                    and isinstance(row.resume, dict)
                    and isinstance(row.cover_letter, dict)
                )
            assert client.get("/documents?job_id=999999").json()["total"] == 0
    finally:
        engine.dispose()


def test_failed_tailoring_recorded(tmp_path: Path) -> None:
    app = create_app(
        tmp_path / "postgres",
        resume_transport=httpx2.MockTransport(
            lambda _request: httpx2.Response(500, text="private provider diagnostics")
        ),
    )
    app.dependency_overrides[resume_ai_settings] = settings
    with TestClient(app) as client:
        client.put("/resumes/profile", json=resume().model_dump())
        job = JobResponse.model_validate_json(
            client.post("/jobs", json={"raw_description": "Build Python APIs"}).content
        )
        client.put(
            f"/jobs/{job.id}/user", json={"status": "interviewing", "notes": "Keep", "version": 0}
        )
        body = {"request_id": str(uuid4()), "include_resume": True, "include_cover_letter": False}
        failed = client.post(f"/jobs/{job.id}/tailor", json=body)
        assert failed.status_code == 502 and "private provider" not in failed.text
        user = JobResponse.model_validate_json(client.get(f"/jobs/{job.id}").content).user
        assert user.status == "interviewing" and user.notes == "Keep" and user.applied_at is None
        assert user.documents[0].status == "failed" and not user.documents[0].has_resume
        assert client.get(f"/documents/{body['request_id']}/resume/pdf").status_code == 409
        assert client.post(f"/jobs/{job.id}/tailor", json=body).status_code == 409


def test_stale_profile_edit_rejected(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "postgres")) as client:
        empty = ResumeProfileState.model_validate_json(client.get("/resumes/manager").content)
        assert empty.resume is None and empty.revision == 0
        original = resume().model_dump()
        assert (
            client.put("/resumes/manager", json={"resume": original, "revision": 0}).status_code
            == 200
        )
        newer = resume()
        newer.projects[0].raw_description += " Additional factual context."
        saved = client.put("/resumes/manager", json={"resume": newer.model_dump(), "revision": 1})
        assert saved.status_code == 200
        assert (
            client.put("/resumes/manager", json={"resume": original, "revision": 1}).status_code
            == 409
        )
        state = ResumeProfileState.model_validate_json(client.get("/resumes/manager").content)
        assert state.revision == 2 and state.resume == newer
        client.put("/resumes/profile", json=original)
        assert (
            client.put(
                "/resumes/manager", json={"resume": newer.model_dump(), "revision": 2}
            ).status_code
            == 409
        )
