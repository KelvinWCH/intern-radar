from collections.abc import Callable, Mapping
from math import ceil, inf
from typing import TypeVar

from job_backend.common.ai_completion import AiCompletionError
from job_backend.resumes.compile_pdf.compile import (
    DocumentLayoutError,
    MeasuredPdf,
    compile_one_page_measured,
    resolve_compiler,
)
from job_backend.resumes.compile_pdf.models import PdfCompiler
from job_backend.resumes.constants import (
    LINE_POINTS,
    MAX_GENERATION_ATTEMPTS,
    MAX_TRIM_COMPILES,
    MIN_FILL_PROGRESS_INCHES,
    MIN_FIT_PROGRESS_POINTS,
    WRAP_POINTS_PER_CHARACTER,
)
from job_backend.resumes.models import GeneratedCoverLetter, GeneratedResume, ProgressCallback
from job_backend.resumes.progress import report_progress
from job_backend.resumes.render_cover_letter.render import cover_letter_to_latex
from job_backend.resumes.render_latex.render import resume_to_latex

Document = TypeVar("Document", GeneratedResume, GeneratedCoverLetter)


class DraftRevisionRequired(ValueError):
    def __init__(
        self,
        feedback: str,
        *,
        summary: str = "Cover-letter opening still fails the writing constraints",
    ) -> None:
        super().__init__(feedback)
        self.summary = summary


class DraftsDidNotFit(DocumentLayoutError):
    def __init__(
        self,
        message: str,
        *,
        draft: GeneratedResume | GeneratedCoverLetter,
        overflow_points: float,
    ) -> None:
        super().__init__(message, overflow_points=overflow_points)
        self.draft = draft
        self.overflow_lines = ceil(overflow_points / LINE_POINTS) if overflow_points > 0 else 0


class _ShortestDraft(DocumentLayoutError):
    def __init__(
        self,
        failure: DocumentLayoutError,
        draft: GeneratedResume | GeneratedCoverLetter,
        *,
        exhausted: bool = False,
    ) -> None:
        super().__init__(
            str(failure),
            wrapped=failure.wrapped,
            dangling=failure.dangling,
            overflow_points=failure.overflow_points,
            bullet_lines=failure.bullet_lines,
        )
        self.draft = draft
        self.revision_note = _overflow_note(draft, failure)
        self.exhausted = exhausted


def document_to_latex(document: GeneratedResume | GeneratedCoverLetter) -> str:
    if isinstance(document, GeneratedResume):
        return resume_to_latex(document)
    return cover_letter_to_latex(document)


def generate_one_page(
    make_draft: Callable[[str], Document],
    *,
    compiler: PdfCompiler | None = None,
    layout_feedback: str | None = None,
    fill_feedback: str | None = None,
    line_feedback: str | None = None,
    retry_style: bool = True,
    feedback: str = "",
    on_style: Callable[[str], None] | None = None,
    on_progress: ProgressCallback | None = None,
    on_pdf: Callable[[Document, bytes], None] | None = None,
    shorten: Callable[[Document, float, Mapping[str, int]], Document | None] | None = None,
) -> Document:
    report_progress(on_progress, "prepare", "Checking the PDF compiler")
    resolved = resolve_compiler(compiler)
    base = feedback
    best: tuple[Document, bytes, tuple[int, float], str] | None = None
    requested_fill_at: float | None = None
    closest: _ShortestDraft | None = None

    def accept(draft: Document, pdf: bytes, style: str = "") -> Document:
        if on_style is not None:
            on_style(style)
        if on_pdf is not None:
            on_pdf(draft, pdf)
        report_progress(on_progress, "validate", "PDF passed one-page validation")
        return draft

    for attempt in range(MAX_GENERATION_ATTEMPTS):
        last = attempt == MAX_GENERATION_ATTEMPTS - 1
        try:
            draft = make_draft(feedback)
            report_progress(on_progress, "compile", "Compiling PDF and checking one-page layout")
            draft, measured = _compile_fitting(draft, shorten, resolved, on_progress)
        except AiCompletionError:
            if best is None:
                raise
            return accept(best[0], best[1], best[3])
        except DraftRevisionRequired as error:
            if last:
                if best is not None:
                    return accept(best[0], best[1], best[3])
                raise AiCompletionError(error.summary) from None
            feedback = base + "\n# Required revision\n" + str(error)
            report_progress(on_progress, "retry", f"Revising writing · draft {attempt + 2} of 3")
            continue
        except DocumentLayoutError as error:
            stalled = (
                isinstance(error, _ShortestDraft)
                and closest is not None
                and error.overflow_points > 0
                and closest.overflow_points > 0
                and error.overflow_points > closest.overflow_points - MIN_FIT_PROGRESS_POINTS
            )
            if isinstance(error, _ShortestDraft) and (
                closest is None or _overrun(error) < _overrun(closest)
            ):
                closest = error
            if last or stalled:
                if best is not None:
                    return accept(best[0], best[1], best[3])
                if closest is not None:
                    lines = ceil(closest.overflow_points / LINE_POINTS)
                    raise DraftsDidNotFit(
                        (
                            "Could not fit one page after three drafts."
                            if last
                            else f"Could not fit one page: draft {attempt + 1} was no shorter "
                            "than the one before, so no more drafts were requested."
                        )
                        + " The closest draft"
                        + (f", about {lines} printed lines too long," if lines > 0 else "")
                        + " is saved so you can read it."
                        + (
                            " Every entry was already down to its minimum bullets, so lower "
                            "the minimums or switch off an entry in your profile, then try again."
                            if closest.exhausted
                            else ""
                        ),
                        draft=closest.draft,
                        overflow_points=closest.overflow_points,
                    ) from None
                raise DocumentLayoutError(
                    "Could not produce a readable one-page document after three drafts. "
                    "Shorten the source metadata or select less content; no document was returned."
                ) from None
            report_progress(on_progress, "retry", f"Tightening page fit · draft {attempt + 2} of 3")
            feedback = base + (
                "\n# Required revision after actual PDF compilation\n"
                + str(error)
                + error.revision_note
                + layout_feedback
                if layout_feedback is not None
                else "\n# Required revision after actual PDF compilation\n"
                + str(error)
                + "\nReturn a complete revised draft with materially less content: "
                "reduce prose and selections by roughly one third on each retry. Keep the most "
                "relevant evidence, the posting's keywords, and all required sections. Use fewer "
                "examples and shorter sentences. Never shrink fonts, change margins, crop pages, "
                "invent abbreviations or facts, or alter copied identity metadata."
            )
            continue
        draft = keep_fitted(draft, measured.fitted)
        problems, note = (
            _line_problems(draft, measured.wrapped, measured.dangling, measured.late)
            if line_feedback is not None
            else (0, "")
        )
        unfilled = fill_feedback is not None and measured.blank_inches > 0
        if not problems and not unfilled:
            return accept(draft, measured.pdf)
        style = "\n# Required revision after actual PDF compilation"
        if problems:
            style += note + (line_feedback or "")
        if unfilled:
            blank = measured.blank_inches
            thin = _wrapped_bullets(draft, measured.short) if line_feedback is not None else []
            # roughly one small resume line per 12pt of empty space
            style += (
                f"\nThe resume fits on one page but leaves about {blank:.1f} inches (roughly "
                f"{max(1, round(blank * 72.27 / 12))} lines) blank at the bottom."
                + (_room_note(thin) if thin else "")
                + (fill_feedback or "")
            )
        if not retry_style:
            return accept(draft, measured.pdf, style)
        score = (problems, measured.blank_inches if unfilled else 0.0)
        if best is None or score < best[2]:
            best = (draft, measured.pdf, score, style)
        stalled = (
            not problems
            and requested_fill_at is not None
            and measured.blank_inches > requested_fill_at - MIN_FILL_PROGRESS_INCHES
        )
        if last or stalled:
            return accept(best[0], best[1], best[3])
        requested_fill_at = measured.blank_inches if unfilled else None
        feedback = base + style
        report_progress(
            on_progress,
            "retry",
            f"{'Fixing bullet line breaks' if problems else 'Filling the page'}"
            f" · draft {attempt + 2} of 3",
        )
    raise RuntimeError("Unreachable generation state")


def _compile_fitting(
    draft: Document,
    shorten: Callable[[Document, float, Mapping[str, int]], Document | None] | None,
    compiler: PdfCompiler,
    on_progress: ProgressCallback | None,
) -> tuple[Document, MeasuredPdf]:
    try:
        return draft, compile_one_page_measured(document_to_latex(draft), compiler=compiler)
    except DocumentLayoutError as error:
        current, failure = draft, error
    exhausted = False
    for _ in range(MAX_TRIM_COMPILES if shorten is not None else 0):
        if shorten is None or not failure.overflow_points:
            break
        shorter = shorten(current, failure.overflow_points, dict(failure.bullet_lines))
        if shorter is None:
            exhausted = True
            break
        report_progress(
            on_progress, "compile", "Dropping the least relevant extra bullets to fit one page"
        )
        try:
            return shorter, compile_one_page_measured(document_to_latex(shorter), compiler=compiler)
        except DocumentLayoutError as error:
            current, failure = shorter, error
    raise _ShortestDraft(failure, current, exhausted=exhausted) from failure


def _overrun(failure: DocumentLayoutError) -> float:
    return failure.overflow_points if failure.overflow_points > 0 else inf


def _overflow_note(
    draft: GeneratedResume | GeneratedCoverLetter | None, failure: DocumentLayoutError
) -> str:
    if not isinstance(draft, GeneratedResume):
        return ""
    if not failure.overflow_points:
        return _line_problems(draft, failure.wrapped, failure.dangling, overflowing=True)[1]
    lines = dict(failure.bullet_lines)
    spill = dict(failure.dangling)
    rows: list[str] = []
    used = 0
    for kind, entries in (("experience", draft.experience), ("project", draft.projects)):
        for entry_index, entry in enumerate(entries):
            for bullet_index, text in enumerate(entry.bullets):
                line_id = f"{kind}-{entry_index}-{bullet_index}"
                count = lines.get(line_id, 1)
                used += count
                detail = f"{count} printed line{'s' if count > 1 else ''}"
                if line_id in spill:
                    characters = ceil(spill[line_id] / WRAP_POINTS_PER_CHARACTER)
                    detail += f", about {characters} characters on the second"
                rows.append(f'\n- "{text}" ({detail})')
    cut = ceil(failure.overflow_points / LINE_POINTS)
    return (
        f"\nWin back at least {cut} printed lines. This draft's experience and project bullets "
        f"use {used} printed lines; plan about {max(used - cut, 0)} in total. A bullet spilling "
        "a few words onto a second line is the cheapest to cut to one line; then rewrite other "
        "two-line bullets as one full line of 90 to 105 characters, least relevant entries first. "
        "This draft's bullets:" + "".join(rows)
    )


def keep_fitted(draft: Document, fitted: tuple[tuple[str, int], ...]) -> Document:
    if not isinstance(draft, GeneratedResume) or not fitted:
        return draft
    counts = dict(fitted)
    return draft.model_copy(
        update={
            "projects": [
                project.model_copy(
                    update={"technologies": project.technologies[: counts.get(f"project-{index}")]}
                )
                for index, project in enumerate(draft.projects)
            ],
            "education": [
                school.model_copy(
                    update={"coursework": school.coursework[: counts.get(f"coursework-{index}")]}
                )
                for index, school in enumerate(draft.education)
            ],
        }
    )


def _wrapped_bullets(
    draft: GeneratedResume | GeneratedCoverLetter | None, wrapped: tuple[tuple[str, float], ...]
) -> list[tuple[str, float]]:
    if not isinstance(draft, GeneratedResume):
        return []
    entries = {"experience": draft.experience, "project": draft.projects}
    bullets: list[tuple[str, float]] = []
    for line_id, overflow in wrapped:
        kind, entry, bullet = line_id.rsplit("-", 2)
        try:
            bullets.append((entries[kind][int(entry)].bullets[int(bullet)], overflow))
        except (KeyError, IndexError, ValueError):
            continue
    return bullets


def _room_note(thin: list[tuple[str, float]]) -> str:
    return (
        "\nThese one-line bullets use under 80% of their line. Lengthen them first with the "
        "supported scale, product context, or second result from the same entry, if the source "
        "has any, either within one line or across most of a second line:"
        + "".join(
            f'\n- "{text}" (room for about {ceil(room / WRAP_POINTS_PER_CHARACTER)} characters)'
            for text, room in thin
        )
    )


def _line_problems(
    draft: GeneratedResume | GeneratedCoverLetter | None,
    wrapped: tuple[tuple[str, float], ...],
    dangling: tuple[tuple[str, float], ...] = (),
    late: tuple[tuple[str, float], ...] = (),
    *,
    overflowing: bool = False,
) -> tuple[int, str]:
    groups = [
        ("These bullets run past two printed lines:", "too long", wrapped),
        (
            "These bullets spill only a few words onto a second printed line. Cut them to one "
            + (
                "line:"
                if overflowing
                else "line, or use most of the second line for supported method, scale, or purpose:"
            ),
            "on the second line",
            dangling,
        ),
        (
            "These bullets print their first number after the first printed line. Move the "
            "number and its plain-language result to the start:",
            "too late",
            late,
        ),
    ]
    count = 0
    note = ""
    for heading, unit, measured in groups:
        bullets = _wrapped_bullets(draft, measured)
        if bullets:
            count += len(bullets)
            note += f"\n{heading}" + "".join(
                f'\n- "{text}" (about {ceil(points / WRAP_POINTS_PER_CHARACTER)} characters {unit})'
                for text, points in bullets
            )
    return count, note
