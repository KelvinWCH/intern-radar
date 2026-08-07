import re
import shutil
import subprocess
from functools import partial
from io import BytesIO
from math import ceil
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import NamedTuple

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from job_backend.resumes.compile_pdf.constants import (
    MAX_COMPILER_NOTE_CHARS,
    MAX_LOG_BYTES,
    MAX_PDF_BYTES,
    MAX_SOURCE_BYTES,
)
from job_backend.resumes.compile_pdf.models import CompiledPdf, PdfCompiler, PdfSettings
from job_backend.resumes.constants import LINE_POINTS


class PdfCompilerError(RuntimeError):
    pass


class _CompilerRunError(PdfCompilerError):
    pass


class DocumentLayoutError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        wrapped: tuple[tuple[str, float], ...] = (),
        dangling: tuple[tuple[str, float], ...] = (),
        overflow_points: float = 0.0,
        bullet_lines: tuple[tuple[str, int], ...] = (),
    ) -> None:
        super().__init__(message)
        self.wrapped = wrapped
        self.dangling = dangling
        self.overflow_points = overflow_points
        self.bullet_lines = bullet_lines
        self.revision_note = ""


class MeasuredPdf(NamedTuple):
    pdf: bytes
    blank_inches: float
    wrapped: tuple[tuple[str, float], ...]
    short: tuple[tuple[str, float], ...] = ()
    dangling: tuple[tuple[str, float], ...] = ()
    late: tuple[tuple[str, float], ...] = ()
    fitted: tuple[tuple[str, int], ...] = ()


class MeasuredDraft(NamedTuple):
    pdf: bytes
    page_count: int
    overflow_points: float
    blank_inches: float
    lines: tuple[tuple[str, int], ...]
    wrapped: tuple[tuple[str, float], ...]
    short: tuple[tuple[str, float], ...]
    dangling: tuple[tuple[str, float], ...]
    late: tuple[tuple[str, float], ...]
    fitted: tuple[tuple[str, int], ...]


def resolve_compiler(compiler: PdfCompiler | None = None) -> PdfCompiler:
    if compiler is not None:
        return compiler
    try:
        settings = PdfSettings.from_environment()
    except ValueError:
        raise PdfCompilerError(
            "Configure valid JOB_LATEX settings before generating documents"
        ) from None
    executable = shutil.which(settings.executable)
    if executable is None:
        raise PdfCompilerError(
            "Install Tectonic or set JOB_LATEX_EXECUTABLE to enable one-page validation"
        )
    return partial(
        _compile, executable=str(Path(executable).resolve()), timeout=settings.timeout_seconds
    )


def compile_one_page(source: str, *, compiler: PdfCompiler | None = None) -> bytes:
    return compile_one_page_measured(source, compiler=compiler)[0]


def compile_one_page_measured(source: str, *, compiler: PdfCompiler | None = None) -> MeasuredPdf:
    result = _compile_validated(source, max_pages=1, compiler=compiler)
    return MeasuredPdf(
        result.pdf,
        _blank_inches(result.log),
        _wrapped(result.log),
        _wrapped(result.log, kind="SHORT"),
        _wrapped(result.log, kind="DANGLE"),
        _wrapped(result.log, kind="LATE"),
        _fitted(result.log),
    )


def compile_draft_measured(
    source: str, *, max_pages: int, compiler: PdfCompiler | None = None
) -> MeasuredDraft:
    result = _compile_validated(source, max_pages=max_pages, compiler=compiler)
    page_count = len(PdfReader(BytesIO(result.pdf), strict=True).pages)
    return MeasuredDraft(
        result.pdf,
        page_count,
        _overflow_points(result.log) if page_count > 1 else 0.0,
        _blank_inches(result.log) if page_count == 1 else 0.0,
        _line_counts(result.log),
        _wrapped(result.log),
        _wrapped(result.log, kind="SHORT"),
        _wrapped(result.log, kind="DANGLE"),
        _wrapped(result.log, kind="LATE"),
        _fitted(result.log),
    )


def _blank_inches(log: str) -> float:
    blank = re.search(r"JOB-RESUME-BLANK: ([0-9.]+)pt", log)
    return float(blank.group(1)) / 72.27 if blank else 0.0


def _fitted(log: str) -> tuple[tuple[str, int], ...]:
    pattern = r"JOB-RESUME-FIT: ((?:project|coursework)-\d+) (\d+)"
    return tuple((match.group(1), int(match.group(2))) for match in re.finditer(pattern, log))


def _line_counts(log: str) -> tuple[tuple[str, int], ...]:
    pattern = r"JOB-RESUME-LINES: ((?:experience|project)-\d+-\d+) (\d+)"
    return tuple((match.group(1), int(match.group(2))) for match in re.finditer(pattern, log))


def _overflow_points(log: str) -> float:
    match = re.search(r"JOB-RESUME-OVERFLOW: (\d+) ([0-9.]+)pt ([0-9.]+)pt", log)
    if match is None:
        return 0.0
    page, used, height = int(match.group(1)), float(match.group(2)), float(match.group(3))
    return (page - 2) * height + used


def _wrapped(log: str, *, kind: str = "WRAP") -> tuple[tuple[str, float], ...]:
    pattern = rf"JOB-RESUME-{kind}: ((?:experience|project)-\d+-\d+) ([0-9.]+)pt"
    return tuple((match.group(1), float(match.group(2))) for match in re.finditer(pattern, log))


def compile_document(
    source: str, *, max_pages: int = 20, compiler: PdfCompiler | None = None
) -> bytes:
    return _compile_validated(source, max_pages=max_pages, compiler=compiler).pdf


def _compile_validated(source: str, *, max_pages: int, compiler: PdfCompiler | None) -> CompiledPdf:
    if not 1 <= max_pages <= 20:
        raise ValueError("PDF page limit must be between 1 and 20")
    if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise DocumentLayoutError("LaTeX source exceeds the 512 KiB limit")
    result = resolve_compiler(compiler)(source)
    if len(result.pdf) > MAX_PDF_BYTES:
        raise DocumentLayoutError("Generated PDF exceeds the 2.5 MB file-size limit")
    try:
        reader = PdfReader(BytesIO(result.pdf), strict=True)
        if reader.is_encrypted:
            raise PdfCompilerError("Compiler produced an encrypted PDF")
        count = len(reader.pages)
        if max_pages == 1 and count != 1:
            overflow = _overflow_points(result.log)
            raise DocumentLayoutError(
                f"Document has {count} pages; exactly one page is required"
                + (
                    f". It runs about {ceil(overflow / LINE_POINTS)} printed lines past the page"
                    if overflow
                    else ""
                ),
                wrapped=_wrapped(result.log),
                dangling=_wrapped(result.log, kind="DANGLE"),
                overflow_points=overflow,
                bullet_lines=_line_counts(result.log),
            )
        if not 1 <= count <= max_pages:
            raise DocumentLayoutError(f"Document has {count} pages; allow 1 to {max_pages} pages")
        texts = [page.extract_text() for page in reader.pages]
    except (PdfReadError, ValueError, KeyError, TypeError, IndexError) as error:
        if isinstance(error, DocumentLayoutError):
            raise
        raise PdfCompilerError("Compiler produced an unreadable PDF") from None
    if any(not text.strip() or "\ufffd" in text for text in texts):
        raise DocumentLayoutError("Generated PDF must contain readable, selectable text")
    if re.search(r"Overfull \\[hv]box", result.log) or "Missing character:" in result.log:
        raise DocumentLayoutError("Document contains overflowing text or missing characters")
    return result


def _compile(source: str, *, executable: str, timeout: float) -> CompiledPdf:
    try:
        return _compile_once(source, executable=executable, timeout=timeout)
    except _CompilerRunError:
        return _compile_once(source, executable=executable, timeout=timeout)


def _compile_once(source: str, *, executable: str, timeout: float) -> CompiledPdf:
    with TemporaryDirectory(prefix="job-resume-") as folder:
        root = Path(folder)
        (root / "main.tex").write_text(source, encoding="utf-8")
        try:
            with (root / "compiler.log").open("wb") as output:
                process = subprocess.run(
                    [executable, "--untrusted", "--keep-logs", "--outdir", str(root), "main.tex"],
                    cwd=root,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                    check=False,
                )
        except subprocess.TimeoutExpired:
            raise PdfCompilerError("LaTeX compilation exceeded JOB_LATEX_TIMEOUT_SECONDS") from None
        except OSError:
            raise PdfCompilerError("The configured LaTeX compiler could not run") from None
        pdf = root / "main.pdf"
        log = root / "main.log"
        if process.returncode != 0 or not pdf.is_file() or not log.is_file():
            error = _CompilerRunError("LaTeX compilation failed; no document was returned")
            output = (root / "compiler.log").read_text(encoding="utf-8", errors="replace")
            error.add_note(
                f"Compiler exit code {process.returncode}; output tail:\n"
                + output[-MAX_COMPILER_NOTE_CHARS:].strip()
            )
            raise error
        if pdf.stat().st_size > MAX_PDF_BYTES:
            raise DocumentLayoutError("Generated PDF exceeds the 2.5 MB file-size limit")
        if log.stat().st_size > MAX_LOG_BYTES:
            raise PdfCompilerError("LaTeX compilation log exceeds the 1 MiB limit")
        return CompiledPdf(
            pdf=pdf.read_bytes(), log=log.read_text(encoding="utf-8", errors="replace")
        )
