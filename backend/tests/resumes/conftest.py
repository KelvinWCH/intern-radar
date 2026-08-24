import pytest
from pytest import MonkeyPatch

from job_backend.resumes import generation
from job_backend.resumes.compile_pdf import compile as pdf_module
from job_backend.resumes.compile_pdf.models import PdfCompiler
from job_backend.resumes.generate_resume.page_budget import clear_page_budget_cache
from tests.resumes.pdf_helpers import one_page_compiler


@pytest.fixture(autouse=True)
def offline_pdf_compiler(monkeypatch: MonkeyPatch) -> None:
    def resolve(compiler: PdfCompiler | None = None) -> PdfCompiler:
        return compiler or one_page_compiler

    monkeypatch.setattr(pdf_module, "resolve_compiler", resolve)
    monkeypatch.setattr(generation, "resolve_compiler", resolve)


@pytest.fixture(autouse=True)
def fresh_page_budget() -> None:
    clear_page_budget_cache()
