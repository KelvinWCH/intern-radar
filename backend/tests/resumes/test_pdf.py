import subprocess
import sys
from pathlib import Path
from typing import BinaryIO

import httpx2
import pytest
from pytest import MonkeyPatch

from job_backend.resumes import generation
from job_backend.resumes.compile_pdf.compile import (
    DocumentLayoutError,
    PdfCompilerError,
    compile_one_page,
)
from job_backend.resumes.compile_pdf.compile import (
    resolve_compiler as native_resolve_compiler,
)
from job_backend.resumes.compile_pdf.models import CompiledPdf
from job_backend.resumes.generate_cover_letter.generate import generate_cover_letter
from job_backend.resumes.generate_resume.generate import generate_resume
from job_backend.resumes.generate_resume.page_budget import PLACEHOLDER_BULLET
from tests.resumes.helpers import completion, job, resume, selection, settings
from tests.resumes.pdf_helpers import pdf_bytes
from tests.resumes.test_cover_letter import letter_content


@pytest.mark.parametrize("pages", [0, 2, 3])
def test_rejects_extra_pages(pages: int) -> None:
    with pytest.raises(DocumentLayoutError, match=f"{pages} pages"):
        compile_one_page("short", compiler=lambda _source: CompiledPdf(pdf_bytes(pages), ""))


def test_compiler_sandbox(
    monkeypatch: MonkeyPatch,
) -> None:
    folders: list[Path] = []

    def run(
        args: list[str],
        *,
        cwd: Path,
        stdin: int,
        stdout: BinaryIO,
        stderr: int,
        timeout: float,
        check: bool,
    ) -> subprocess.CompletedProcess[bytes]:
        folders.append(cwd)
        assert "--untrusted" in args and args[-1] == "main.tex"
        assert stdin == subprocess.DEVNULL and stderr == subprocess.STDOUT
        assert timeout == 30.0 and not check
        assert stdout.writable() and (cwd / "main.tex").read_text() == "safe source"
        (cwd / "main.pdf").write_bytes(pdf_bytes())
        (cwd / "main.log").write_text("No layout problems")
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setenv("JOB_LATEX_EXECUTABLE", sys.executable)
    monkeypatch.setenv("JOB_LATEX_TIMEOUT_SECONDS", "30")
    result = native_resolve_compiler()("safe source")
    assert result.pdf == pdf_bytes()
    assert len(folders) == 1 and not folders[0].exists()


@pytest.mark.parametrize("kind", ["resume", "letter"])
def test_overflow_stops_after_three(kind: str) -> None:
    calls = 0

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        content = selection() if kind == "resume" else letter_content()
        return completion(content.model_dump_json())

    generate = generate_resume if kind == "resume" else generate_cover_letter
    with pytest.raises(DocumentLayoutError, match="after three drafts"):
        generate(
            job(),
            resume=resume(),
            settings=settings(),
            transport=httpx2.MockTransport(handler),
            compiler=lambda source: CompiledPdf(
                pdf_bytes(1 if PLACEHOLDER_BULLET in source else 2), ""
            ),
        )
    assert calls == 3


def test_missing_compiler(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("JOB_LATEX_EXECUTABLE", "nonexistent-compiler-for-this-test")
    monkeypatch.setattr(generation, "resolve_compiler", native_resolve_compiler)

    def handler(_request: httpx2.Request) -> httpx2.Response:
        pytest.fail("A missing compiler must not waste a model request")

    with pytest.raises(PdfCompilerError, match="Install Tectonic"):
        generate_resume(
            job(), resume=resume(), settings=settings(), transport=httpx2.MockTransport(handler)
        )
