import httpx2
import pytest

from job_backend.profile.models import ResumeSettings
from job_backend.resumes.compile_pdf.compile import DocumentLayoutError
from job_backend.resumes.compile_pdf.models import CompiledPdf, PdfCompiler
from job_backend.resumes.generate_resume.generate import generate_resume
from tests.resumes.helpers import candidate_profile, completion, job, selection, settings
from tests.resumes.pdf_helpers import pdf_bytes


def counting_compiler(log: str, pages: int) -> tuple[list[str], PdfCompiler]:
    sources: list[str] = []

    def compile_source(source: str) -> CompiledPdf:
        sources.append(source)
        return CompiledPdf(pdf=pdf_bytes(pages), log=log)

    return sources, compile_source


def test_overflow_blocked_early() -> None:
    calls: list[int] = []

    def handler(_request: httpx2.Request) -> httpx2.Response:
        calls.append(1)
        return completion(selection().model_dump_json())

    _, compiler = counting_compiler("JOB-RESUME-OVERFLOW: 2 36.0pt 723.0pt", 2)
    profile = candidate_profile()
    profile.experience[0].bullets = ["Built Python APIs.", "Added caching.", "Wrote tests."]
    profile.projects[0].bullets = ["Built a search service.", "Benchmarked 500 queries."]
    profile.resume_settings = ResumeSettings(min_experience_bullets=3, min_project_bullets=2)
    with pytest.raises(DocumentLayoutError) as caught:
        generate_resume(
            job(),
            resume=profile,
            settings=settings(),
            transport=httpx2.MockTransport(handler),
            compiler=compiler,
        )
    message = str(caught.value)
    assert "shortest resume your settings allow runs about 3 printed lines past one page" in message
    assert "no tokens were spent" in message
    assert "lowering the experience minimum from 3" in message
    assert "lowering the project minimum from 2" in message
    assert "switching off an entry" in message
    assert calls == []
