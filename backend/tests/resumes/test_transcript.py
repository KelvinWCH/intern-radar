from io import BytesIO
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter

from job_backend.jobs.models import JobDocument
from job_backend.jobs.user_routes import create_router as create_user_router
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.resumes.models import GeneratedCoverLetter
from job_backend.resumes.routes import create_router as create_resumes_router
from tests.resumes.test_render import generated_resume


def blank_pdf(pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def client(engine: Database) -> TestClient:
    app = FastAPI()
    app.include_router(create_resumes_router(engine))
    app.include_router(create_user_router(engine))
    return TestClient(app)


def save_attempt(engine: Database, *, letter: bool = True) -> None:
    resume = generated_resume()
    cover_letter = GeneratedCoverLetter(
        name=resume.name,
        email=resume.email,
        phone=resume.phone,
        location=resume.location,
        links=[],
        company="Target Employer",
        job_title="Backend Intern",
        greeting="Dear Hiring Manager,",
        paragraphs=["First paragraph.", "Second paragraph.", "Third paragraph."],
        closing="Sincerely,",
    )
    with Session(engine) as session, session.begin():
        session.add(
            JobDocument(
                id="document",
                job_id="target",
                company="Target Employer",
                status="completed",
                has_resume=True,
                has_cover_letter=letter,
                resume=resume.model_dump(mode="json"),
                cover_letter=cover_letter.model_dump(mode="json") if letter else None,
            )
        )


def test_transcript_upload(engine: Database) -> None:
    with client(engine) as api:
        assert api.get("/resumes/transcript").json() is None
        saved = api.put(
            "/resumes/transcript", files={"file": ("grades.pdf", blank_pdf(2), "application/pdf")}
        )
        assert saved.status_code == 200
        assert saved.json()["filename"] == "grades.pdf"
        assert saved.json()["page_count"] == 2
        assert api.get("/resumes/transcript").json()["size"] == len(blank_pdf(2))
        download = api.get("/resumes/transcript/pdf")
        assert download.status_code == 200
        assert download.content == blank_pdf(2)
        assert 'filename="Transcript.pdf"' in download.headers["content-disposition"]
        assert api.delete("/resumes/transcript").status_code == 204
        assert api.get("/resumes/transcript").json() is None
        assert api.get("/resumes/transcript/pdf").status_code == 404


def test_package_pdf(engine: Database) -> None:
    save_attempt(engine)
    with (
        client(engine) as api,
        patch("job_backend.jobs.user_routes.compile_one_page", return_value=blank_pdf()),
    ):
        api.put("/resumes/transcript", files={"file": ("t.pdf", blank_pdf(3), "application/pdf")})
        response = api.get("/documents/document/package")
        without = api.get("/documents/document/package", params={"transcript": "false"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "_Application.pdf" in response.headers["content-disposition"]
    assert len(PdfReader(BytesIO(response.content)).pages) == 5
    assert len(PdfReader(BytesIO(without.content)).pages) == 2
