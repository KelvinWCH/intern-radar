import json
import re
from collections.abc import Callable
from math import ceil

import httpx2
from pydantic import Field, JsonValue

from job_backend.common.ai_completion import AiCompletionError, complete_json
from job_backend.common.models import AiSettings, AiUsage, CompletionOutput, StrictModel
from job_backend.resumes.compile_pdf.compile import DocumentLayoutError, compile_one_page_measured
from job_backend.resumes.compile_pdf.models import PdfCompiler
from job_backend.resumes.constants import WRAP_POINTS_PER_CHARACTER
from job_backend.resumes.generate_resume.constants import BULLET_FIX_PROMPT
from job_backend.resumes.models import GeneratedResume, ResumeText, UserResume
from job_backend.resumes.render_latex.render import first_metric, resume_to_latex
from job_backend.resumes.text_match import loose_text

REPEAT_OVERLAP = 0.6
_STOP_WORDS = frozenset(
    "a an the and or of to for in on with by from at as that this into over its their".split()
)


class BulletFix(StrictModel):
    """one rewritten bullet, named by the template line id"""

    line_id: str
    text: ResumeText


class BulletFixes(StrictModel):
    """every flagged bullet rewritten, the rest stay as they are"""

    bullets: list[BulletFix] = Field(default_factory=list[BulletFix])


def fix_flagged_bullets(
    document: GeneratedResume,
    source: UserResume,
    settings: AiSettings,
    *,
    compiler: PdfCompiler | None = None,
    transport: httpx2.BaseTransport | None = None,
    on_usage: Callable[[AiUsage], None] | None = None,
    on_output: Callable[[CompletionOutput], None] | None = None,
    on_report: Callable[[dict[str, JsonValue]], None] | None = None,
) -> tuple[GeneratedResume, bytes, int] | None:
    try:
        measured = compile_one_page_measured(resume_to_latex(document), compiler=compiler)
    except DocumentLayoutError:
        return None
    flagged = {
        **{
            line_id: ("runs past two printed lines", points) for line_id, points in measured.wrapped
        },
        **{
            line_id: ("spills only a few words onto a second line", points)
            for line_id, points in measured.dangling
        },
        **{
            line_id: ("prints its first number after the first line", points)
            for line_id, points in measured.late
        },
    }
    if not flagged:
        return None
    entries = _entries(document)
    sources = {
        **{f"experience-{i}": item.raw_description for i, item in enumerate(source.experience)},
        **{f"project-{i}": item.raw_description for i, item in enumerate(source.projects)},
    }
    requests: list[dict[str, JsonValue]] = []
    for line_id, (problem, points) in flagged.items():
        entry_id, index = line_id.rsplit("-", 1)
        name, bullets = entries[entry_id]
        requests.append(
            {
                "line_id": line_id,
                "entry": name,
                "problem": f"{problem}, by about {ceil(points / WRAP_POINTS_PER_CHARACTER)} "
                "characters",
                "bullet": bullets[int(index)],
                "sibling_bullets_already_said": [
                    text for i, text in enumerate(bullets) if i != int(index)
                ],
                "source_text": sources.get(entry_id, ""),
            }
        )
    try:
        fixes = complete_json(
            settings,
            system_prompt=BULLET_FIX_PROMPT,
            user_content=json.dumps({"bullets": requests}, ensure_ascii=False),
            response_model=BulletFixes,
            schema_name="bullet_fixes",
            transport=transport,
            on_usage=on_usage,
            on_output=on_output,
            on_report=on_report,
        )
    except AiCompletionError:
        return None
    fixed = document.model_copy(deep=True)
    applied = 0
    for fix in fixes.bullets:
        if fix.line_id not in flagged:
            continue
        entry_id, index = fix.line_id.rsplit("-", 1)
        _, bullets = _entries(fixed)[entry_id]
        position = int(index)
        siblings = [text for i, text in enumerate(bullets) if i != position]
        if _keeps_number(bullets[position], fix.text) and not _repeats(fix.text, siblings):
            bullets[position] = " ".join(fix.text.split())
            applied += 1
    if not applied:
        return None
    try:
        remeasured = compile_one_page_measured(resume_to_latex(fixed), compiler=compiler)
    except DocumentLayoutError:
        return None
    remaining = len(remeasured.wrapped) + len(remeasured.dangling) + len(remeasured.late)
    if remaining >= len(flagged):
        return None
    return fixed, remeasured.pdf, remaining


def _entries(document: GeneratedResume) -> dict[str, tuple[str, list[str]]]:
    return {
        **{
            f"experience-{i}": (f"{item.title}, {item.company}", item.bullets)
            for i, item in enumerate(document.experience)
        },
        **{f"project-{i}": (item.name, item.bullets) for i, item in enumerate(document.projects)},
    }


def _keeps_number(original: str, replacement: str) -> bool:
    metric = first_metric(original)
    return metric is None or metric.group() in replacement


def _words(text: str) -> set[str]:
    return {word for word in loose_text(text).split() if word not in _STOP_WORDS}


def _repeats(candidate: str, siblings: list[str]) -> bool:
    words = _words(candidate)
    metric = first_metric(candidate)
    lead = re.match(r"\s*(\w+)", candidate)
    for sibling in siblings:
        other = first_metric(sibling)
        other_lead = re.match(r"\s*(\w+)", sibling)
        if (
            metric is not None
            and other is not None
            and metric.group() == other.group()
            and lead is not None
            and other_lead is not None
            and lead.group(1).casefold() == other_lead.group(1).casefold()
        ):
            return True
        sibling_words = _words(sibling)
        if words and sibling_words:
            overlap = len(words & sibling_words) / len(words | sibling_words)
            if overlap >= REPEAT_OVERLAP:
                return True
    return False
