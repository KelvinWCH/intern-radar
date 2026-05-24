from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import httpx2
import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from job_backend.jobs.models import DocumentDetail, JobResponse, TailorRequest
from job_backend.jobs.tailoring import get_document, prepare_tailoring
from job_backend.jobs.user_service import EditConflictError
from job_backend.main import create_app
from job_backend.persistence.database import make_engine
from job_backend.resumes.compile_pdf.models import CompiledPdf, PdfCompiler
from job_backend.resumes.dependencies import resume_ai_settings
from tests.resumes.helpers import completion_event, resume, selection, settings, workflow_response
from tests.resumes.pdf_helpers import pdf_bytes


def test_background_progress(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    database = tmp_path / "postgres"
    engine = make_engine(database)
    request_id = str(uuid4())
    calls = 0
    compilations = 0

    def compiler(_source: str) -> CompiledPdf:
        nonlocal compilations
        compilations += 1
        return CompiledPdf(pdf=pdf_bytes(2 if compilations == 1 else 1), log="")

    def resolve(_compiler: PdfCompiler | None = None) -> PdfCompiler:
        return compiler

    monkeypatch.setattr("job_backend.resumes.generation.resolve_compiler", resolve)

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        research = workflow_response(_request)
        if research is not None:
            return research
        calls += 1
        pending = get_document(engine, request_id)
        assert pending.status == "running" and pending.resume is None
        assert pending.events[-1].stage == "ai"
        replay = prepare_tailoring(
            engine, pending.job_id, TailorRequest(request_id=request_id), settings()
        )
        assert isinstance(replay, DocumentDetail) and replay.status == "running"
        with pytest.raises(EditConflictError):
            prepare_tailoring(
                engine, pending.job_id, TailorRequest(request_id=str(uuid4())), settings()
            )
        draft = selection().model_dump_json()

        class Stream(httpx2.SyncByteStream):
            def __iter__(self) -> Iterator[bytes]:
                yield completion_event(draft[:30])
                live = get_document(engine, request_id)
                assert live.status == "running" and live.resume is None
                assert live.events[-1].stage == "output" and live.events[-1].output == draft[:30]
                yield completion_event(draft[30:], finish="stop")
                yield b"data: [DONE]\n\n"

        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, stream=Stream())

    app = create_app(database, resume_transport=httpx2.MockTransport(handler))
    app.dependency_overrides[resume_ai_settings] = settings
    with TestClient(app) as client:
        client.put("/resumes/profile", json=resume().model_dump())
        job = JobResponse.model_validate_json(
            client.post("/jobs", json={"raw_description": "Build Python APIs"}).content
        )
        body = {"request_id": request_id, "include_cover_letter": False}
        response = client.post(f"/jobs/{job.id}/tailor-tasks", json=body)
        assert response.status_code == 202
        accepted = DocumentDetail.model_validate_json(response.content)
        assert accepted.status == "running" and accepted.events[0].stage == "queued"
        result = DocumentDetail.model_validate_json(client.get(f"/documents/{request_id}").content)
        assert result.status == "completed" and result.resume is not None, result.events[-1].details
        assert calls == 2 and compilations == 2
        stages = [event.stage for event in result.events]
        assert stages.count("ai") == 3 and "retry" in stages
        assert stages[-1] == "done"
        assert [event.id for event in result.events] == list(range(1, len(result.events) + 1))
        assert result.ai_usage is not None and result.ai_usage.calls == 5
        output_events = [event for event in result.events if event.stage == "output"]
        assert len(output_events) == 5
        assert [event.output for event in output_events if event.message.startswith("Resume")] == [
            selection().model_dump_json(),
            selection().model_dump_json(),
        ]
        replay = client.post(f"/jobs/{job.id}/tailor-tasks", json=body)
        assert DocumentDetail.model_validate_json(replay.content) == result and calls == 2
        assert client.get(f"/jobs/{job.id}").json()["user"]["status"] == "saved"
    engine.dispose()


def test_background_failure(tmp_path: Path) -> None:
    calls = 0

    def fail(_request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(
            500, text="private provider diagnostics", headers={"x-request-id": "request-example"}
        )

    app = create_app(tmp_path / "postgres", resume_transport=httpx2.MockTransport(fail))
    app.dependency_overrides[resume_ai_settings] = settings
    with TestClient(app) as client:
        client.put("/resumes/profile", json=resume().model_dump())
        job = JobResponse.model_validate_json(
            client.post("/jobs", json={"raw_description": "Build Python APIs"}).content
        )
        body = {"request_id": str(uuid4()), "include_cover_letter": False}
        assert client.post(f"/jobs/{job.id}/tailor-tasks", json=body).status_code == 202
        result = DocumentDetail.model_validate_json(
            client.get(f"/documents/{body['request_id']}").content
        )
        assert result.status == "failed" and result.events[-1].stage == "error"
        assert result.resume is None
        assert result.error is not None and "private provider" not in result.error
        details = result.events[-1].details
        assert details is not None
        assert "private provider diagnostics" in details
        assert "request-example" in details
        assert "Traceback (most recent call last)" in details
        replay = DocumentDetail.model_validate_json(
            client.get(f"/documents/{body['request_id']}").content
        )
        assert replay.events[-1].details == details
        assert client.get(f"/jobs/{job.id}").json()["user"]["status"] == "new"
        assert client.post(f"/jobs/{job.id}/tailor-tasks", json=body).status_code == 202
        assert calls == 2
        assert (
            client.post(
                f"/jobs/{job.id}/tailor-tasks", json={**body, "request_id": str(uuid4())}
            ).status_code
            == 202
        )
        assert calls == 4
