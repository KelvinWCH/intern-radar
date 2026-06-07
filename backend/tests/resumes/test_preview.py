from dataclasses import fields
from pathlib import Path

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from job_backend.main import create_app
from job_backend.persistence.database import make_engine
from job_backend.persistence.session import Session
from job_backend.resumes.compile_pdf import compile as pdf_module
from job_backend.resumes.compile_pdf.models import CompiledPdf, PdfCompiler
from job_backend.resumes.models import ResumeRecord
from tests.resumes.helpers import resume
from tests.resumes.pdf_helpers import pdf_bytes


def test_preview_route(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("JOB_AI_BASE_URL", raising=False)
    monkeypatch.delenv("JOB_AI_MODEL", raising=False)
    sources: list[str] = []

    def compiler(source: str) -> CompiledPdf:
        sources.append(source)
        return CompiledPdf(pdf_bytes(2), "")

    def resolve(value: PdfCompiler | None = None) -> PdfCompiler:
        return value or compiler

    monkeypatch.setattr(pdf_module, "resolve_compiler", resolve)
    database = tmp_path / "postgres"
    engine = make_engine(database)
    try:
        with TestClient(create_app(database)) as client:
            assert client.get("/resumes/profile/pdf").status_code == 404
            profile = resume()
            assert client.put("/resumes/profile", json=profile.model_dump()).status_code == 200
            with Session(engine) as session:
                before = session.get(ResumeRecord, 1)
            response = client.get("/resumes/profile/pdf")
            assert response.status_code == 200 and response.content == pdf_bytes(2)
            assert response.headers["content-type"] == "application/pdf"
            assert response.headers["content-disposition"] == 'inline; filename="source-resume.pdf"'
            assert response.headers["cache-control"] == "private, no-store"
            assert response.headers["x-content-type-options"] == "nosniff"
            with Session(engine) as session:
                after = session.get(ResumeRecord, 1)
            assert before == after
            assert {field.name for field in fields(ResumeRecord)} == {
                "id",
                "data",
                "updated_at",
                "revision",
            }
            profile.name = "Updated Example"
            client.put("/resumes/profile", json=profile.model_dump())
            assert client.get("/resumes/profile/pdf").status_code == 200
        assert len(sources) == 2
        assert "Alex Example" in sources[0] and "Updated Example" in sources[1]
    finally:
        engine.dispose()
