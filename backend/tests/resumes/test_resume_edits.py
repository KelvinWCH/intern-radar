from dataclasses import replace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import JsonValue
from pytest import MonkeyPatch

from job_backend.common.models import AiUsage
from job_backend.jobs.models import DocumentDetail, JobDocument
from job_backend.jobs.user_routes import create_router as create_user_router
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.resumes.compile_pdf import compile as pdf_module
from job_backend.resumes.compile_pdf.models import CompiledPdf, PdfCompiler
from job_backend.resumes.models import GeneratedResume
from job_backend.resumes.review.review import document_hash
from job_backend.resumes.routes import create_router as create_resumes_router
from tests.resumes.helpers import candidate_profile, job
from tests.resumes.pdf_helpers import pdf_bytes
from tests.resumes.test_render import generated_resume


def compiler(log: str = "", pages: int = 1) -> PdfCompiler:
    def compile_source(_source: str) -> CompiledPdf:
        return CompiledPdf(pdf=pdf_bytes(pages), log=log)

    return compile_source


def use_compiler(monkeypatch: MonkeyPatch, chosen: PdfCompiler) -> list[str]:
    sources: list[str] = []

    def record(source: str) -> CompiledPdf:
        sources.append(source)
        return chosen(source)

    def resolve(_compiler: PdfCompiler | None = None) -> PdfCompiler:
        return record

    monkeypatch.setattr(pdf_module, "resolve_compiler", resolve)
    return sources


def saved_attempt(engine: Database, **fields: object) -> GeneratedResume:
    resume = generated_resume()
    resume.ai_usage = AiUsage(model_name="fictional", calls=1, input_tokens=100, output_tokens=20)
    attempt = JobDocument(
        id="attempt",
        job_id="target",
        company="Target Employer",
        title="Backend Intern",
        status="completed",
        has_resume=True,
        resume=resume.model_dump(mode="json"),
        profile_snapshot=candidate_profile().model_dump(mode="json"),
        target_snapshot=job().model_dump(mode="json"),
        stages=[
            {
                "key": "resume",
                "label": "Resume",
                "model": "fictional",
                "status": "completed",
                "message": "Resume saved",
            }
        ],
    )
    with Session(engine) as session, session.begin():
        session.add(replace(attempt, **fields))
    return resume


def client_for(engine: Database) -> TestClient:
    app = FastAPI()
    app.include_router(create_user_router(engine))
    app.include_router(create_resumes_router(engine))
    return TestClient(app)


def edit_body(resume: GeneratedResume, revision: int = 0) -> dict[str, JsonValue]:
    return {"revision": revision, "resume": resume.model_dump(mode="json")}


def test_saved_edits_kept(engine: Database, monkeypatch: MonkeyPatch) -> None:
    original = saved_attempt(engine)
    sources = use_compiler(monkeypatch, compiler())
    edited = original.model_copy(deep=True)
    edited.experience[0].bullets = ["Cut p95 latency 25% by caching Python API reads in Redis"]
    edited.ai_usage = None
    with client_for(engine) as client:
        response = client.put("/documents/attempt/resume", json=edit_body(edited))
        assert response.status_code == 200, response.text
        saved = DocumentDetail.model_validate_json(response.content)
        latex = client.get("/documents/attempt/resume/tex")
    assert saved.resume is not None and saved.resume.experience[0].bullets == [
        "Cut p95 latency 25% by caching Python API reads in Redis"
    ]
    assert saved.resume.ai_usage == original.ai_usage
    assert saved.generated_resume is not None
    assert document_hash(saved.generated_resume) == document_hash(original)
    assert saved.resume_edited_at is not None and saved.resume_revision == 1
    checks = [report for report in saved.pdf_diagnostics if report.document == "resume"]
    assert [report.document_sha256 for report in checks] == [document_hash(saved.resume)]
    assert len(sources) == 1 and "Cut p95 latency 25\\%" in sources[0]
    assert latex.status_code == 200 and "Cut p95 latency 25\\%" in latex.text


def test_old_save_cannot_overwrite(engine: Database, monkeypatch: MonkeyPatch) -> None:
    original = saved_attempt(engine)
    use_compiler(monkeypatch, compiler())
    first = original.model_copy(deep=True)
    first.skills[0].items = ["Python", "Redis"]
    stale = original.model_copy(deep=True)
    stale.skills[0].items = ["TypeScript"]
    with client_for(engine) as client:
        assert client.put("/documents/attempt/resume", json=edit_body(first)).status_code == 200
        refused = client.put("/documents/attempt/resume", json=edit_body(stale))
        saved = DocumentDetail.model_validate_json(client.get("/documents/attempt").content)
    assert refused.status_code == 409 and "saved again" in refused.json()["detail"]
    assert saved.resume is not None and saved.resume.skills[0].items == ["Python", "Redis"]
    assert saved.resume_revision == 1


def test_overflowing_edit_rejected(engine: Database, monkeypatch: MonkeyPatch) -> None:
    original = saved_attempt(engine)
    use_compiler(monkeypatch, compiler("JOB-RESUME-OVERFLOW: 2 30.0pt 723.0pt", pages=2))
    longer = original.model_copy(deep=True)
    longer.experience[0].bullets.append("Another long accomplishment")
    with client_for(engine) as client:
        response = client.put("/documents/attempt/resume", json=edit_body(longer))
        saved = DocumentDetail.model_validate_json(client.get("/documents/attempt").content)
    assert response.status_code == 422
    assert "about 3 printed lines past one page" in response.json()["detail"]
    assert saved.resume is not None and document_hash(saved.resume) == document_hash(original)
    assert saved.generated_resume is None and saved.resume_revision == 0
