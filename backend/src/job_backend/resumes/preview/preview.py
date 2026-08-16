from base64 import b64encode
from math import ceil
from typing import Literal

from job_backend.profile.tailoring import enabled_entries
from job_backend.resumes.compile_pdf.compile import compile_document, compile_draft_measured
from job_backend.resumes.compile_pdf.models import PdfCompiler
from job_backend.resumes.constants import (
    LINE_POINTS,
    UNFITTED_DRAFT_PAGES,
    WRAP_POINTS_PER_CHARACTER,
)
from job_backend.resumes.models import (
    BulletLayout,
    DraftPreview,
    FittedLine,
    GeneratedResume,
    UserResume,
)
from job_backend.resumes.render_latex.render import resume_to_latex

LineIssue = Literal["wrapped", "dangling", "late", "short"]


def preview_resume(resume: UserResume, *, compiler: PdfCompiler | None = None) -> bytes:
    return compile_document(resume_to_latex(enabled_entries(resume)), compiler=compiler)


def preview_draft(resume: GeneratedResume, *, compiler: PdfCompiler | None = None) -> DraftPreview:
    measured = compile_draft_measured(
        resume_to_latex(resume), max_pages=UNFITTED_DRAFT_PAGES, compiler=compiler
    )
    issues: dict[str, tuple[LineIssue, float]] = {}
    groups: tuple[tuple[LineIssue, tuple[tuple[str, float], ...]], ...] = (
        ("short", measured.short),
        ("late", measured.late),
        ("dangling", measured.dangling),
        ("wrapped", measured.wrapped),
    )
    for issue, lines in groups:
        for line_id, points in lines:
            issues[line_id] = (issue, points)
    bullets: dict[str, BulletLayout] = {}
    for line_id, count in measured.lines:
        kind, entry, bullet = line_id.rsplit("-", 2)
        issue, points = issues.get(line_id, (None, 0.0))
        bullets[line_id] = BulletLayout(
            section="experience" if kind == "experience" else "projects",
            entry=int(entry),
            bullet=int(bullet),
            lines=count,
            issue=issue,
            characters=ceil(points / WRAP_POINTS_PER_CHARACTER) if issue else 0,
        )
    fitted: list[FittedLine] = []
    for line_id, printed in measured.fitted:
        kind, entry = line_id.rsplit("-", 1)
        fitted.append(
            FittedLine(
                section="projects" if kind == "project" else "education",
                entry=int(entry),
                printed=printed,
            )
        )
    return DraftPreview(
        pdf_base64=b64encode(measured.pdf).decode("ascii"),
        page_count=measured.page_count,
        overflow_lines=ceil(measured.overflow_points / LINE_POINTS),
        blank_inches=round(measured.blank_inches, 2),
        bullets=list(bullets.values()),
        fitted=fitted,
    )
