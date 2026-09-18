import pytest

from job_backend.resumes.compile_pdf.models import CompiledPdf, PdfCompiler
from job_backend.resumes.generate_resume.constants import LAYOUT_FEEDBACK, LINE_FEEDBACK
from job_backend.resumes.generation import DraftsDidNotFit, generate_one_page
from job_backend.resumes.models import GeneratedResume
from tests.resumes.pdf_helpers import pdf_bytes
from tests.resumes.test_render import generated_resume


def overflowing(*points: float) -> PdfCompiler:
    amounts = iter(points)

    def compile_source(_source: str) -> CompiledPdf:
        return CompiledPdf(
            pdf=pdf_bytes(2), log=f"JOB-RESUME-OVERFLOW: 2 {next(amounts)}pt 723.0pt"
        )

    return compile_source


def test_keeps_closest_draft() -> None:
    requests: list[str] = []

    def make_draft(feedback: str) -> GeneratedResume:
        requests.append(feedback)
        draft = generated_resume()
        draft.experience[0].bullets = [f"Draft {len(requests)} bullet"]
        return draft

    with pytest.raises(DraftsDidNotFit) as caught:
        generate_one_page(
            make_draft,
            compiler=overflowing(60.0, 20.0, 40.0),
            layout_feedback=LAYOUT_FEEDBACK,
            line_feedback=LINE_FEEDBACK,
        )
    kept = caught.value.draft
    assert isinstance(kept, GeneratedResume) and kept.experience[0].bullets == ["Draft 2 bullet"]
    assert caught.value.overflow_lines == 2
    assert "about 2 printed lines too long" in str(caught.value)
    assert "saved so you can read it" in str(caught.value)
