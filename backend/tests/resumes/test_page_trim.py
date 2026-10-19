from collections.abc import Callable, Mapping

from job_backend.profile.models import ResumeSettings
from job_backend.resumes.compile_pdf.models import CompiledPdf, PdfCompiler
from job_backend.resumes.generate_resume.constants import LAYOUT_FEEDBACK, LINE_FEEDBACK
from job_backend.resumes.generate_resume.fit_page import trim_to_page
from job_backend.resumes.generation import generate_one_page
from job_backend.resumes.models import GeneratedResume
from tests.resumes.helpers import resume
from tests.resumes.pdf_helpers import pdf_bytes
from tests.resumes.test_render import generated_resume

TEXT_HEIGHT = "723.0pt"


def overflow(points: float, page: int = 2, lines: str = "") -> str:
    return f"JOB-RESUME-OVERFLOW: {page} {points}pt {TEXT_HEIGHT}\n{lines}"


def compiles(*outputs: str | None) -> PdfCompiler:
    queue = iter(outputs)

    def compile_source(_source: str) -> CompiledPdf:
        log = next(queue)
        return CompiledPdf(pdf=pdf_bytes(1 if log is None else 2), log=log or "")

    return compile_source


def long_resume() -> GeneratedResume:
    document = generated_resume()
    document.experience[0].bullets = [f"Experience bullet {index}" for index in range(4)]
    document.projects[0].bullets = [f"Project bullet {index}" for index in range(3)]
    return document


def trim(
    document: GeneratedResume, points: float, lines: Mapping[str, int] | None = None
) -> GeneratedResume | None:
    return trim_to_page(document, points, lines or {}, ResumeSettings(), resume())


def test_trims_least_relevant_bullet() -> None:
    trimmed = trim(long_resume(), 20.0)
    assert trimmed is not None
    assert trimmed.experience[0].bullets == [f"Experience bullet {index}" for index in range(4)]
    assert trimmed.projects[0].bullets == ["Project bullet 0", "Project bullet 1"]


def test_minimums_never_cut() -> None:
    document = long_resume()
    document.experience[0].bullets = document.experience[0].bullets[:3]
    document.projects[0].bullets = document.projects[0].bullets[:2]
    document.education[0].coursework = ["Operating Systems"]
    trimmed = trim(document, 100.0)
    assert trimmed is not None and trimmed.education[0].coursework == []
    assert len(trimmed.experience[0].bullets) == 3 and len(trimmed.projects[0].bullets) == 2
    assert trim(trimmed, 100.0) is None
    profile = resume()
    profile.education[0].coursework = ["Operating Systems"]
    profile.education[0].available_coursework = ["Operating Systems"]
    assert trim_to_page(document, 100.0, {}, ResumeSettings(), profile) is None


def drafts(document: GeneratedResume, requests: list[str]) -> Callable[[str], GeneratedResume]:
    def make_draft(feedback: str) -> GeneratedResume:
        requests.append(feedback)
        return document.model_copy(deep=True)

    return make_draft


def test_overflow_trimmed() -> None:
    requests: list[str] = []
    result = generate_one_page(
        drafts(long_resume(), requests),
        compiler=compiles(overflow(20.0), None),
        layout_feedback=LAYOUT_FEEDBACK,
        line_feedback=LINE_FEEDBACK,
        retry_style=False,
        shorten=lambda document, points, lines: trim(document, points, lines),
    )
    assert len(requests) == 1
    assert result.projects[0].bullets == ["Project bullet 0", "Project bullet 1"]
