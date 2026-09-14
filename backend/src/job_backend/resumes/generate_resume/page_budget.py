import hashlib
from collections import OrderedDict
from dataclasses import dataclass
from math import ceil, floor
from threading import Lock

from job_backend.profile.models import ResumeSettings
from job_backend.resumes.compile_pdf.compile import DocumentLayoutError, compile_one_page_measured
from job_backend.resumes.compile_pdf.models import PdfCompiler
from job_backend.resumes.constants import LINE_POINTS
from job_backend.resumes.generate_resume.skills import compact_skill_lines
from job_backend.resumes.models import GeneratedResume, ResumeContent, SkillGroup, UserResume
from job_backend.resumes.render_latex.render import resume_to_latex

PLACEHOLDER_BULLET = "Placeholder bullet"
CACHE_SIZE = 64


@dataclass(frozen=True)
class PageBudget:
    minimum_lines: int
    spare_lines: int
    overflow_lines: int
    entries: tuple[tuple[str, str, int], ...]

    @property
    def fits(self) -> bool:
        return self.overflow_lines == 0

    @property
    def two_line_bullets(self) -> int:
        return min(self.spare_lines, self.minimum_lines)

    def allowance(self) -> str:
        return (
            f"You have {self.spare_lines} extra printed lines to spend across the experience "
            "and project bullets, and no more: a bullet that takes two lines spends one, a "
            "bullet added above an entry's minimum spends one if it takes one line and two if "
            f"it takes two. With the minimum {self.minimum_lines} bullets, at most "
            f"{self.two_line_bullets} of them may take two lines"
            + (
                f", leaving {self.spare_lines - self.minimum_lines} lines for added bullets."
                if self.spare_lines > self.minimum_lines
                else "; every other bullet is one full line of 90 to 105 characters, and each "
                "added bullet takes a two-line allowance away."
            )
            + " Spending more will not fit, and the application then cuts added bullets, "
            "least relevant first."
        )

    def blocking_message(self, minimums: ResumeSettings) -> str:
        experience = [count for section, _, count in self.entries if section == "experience"]
        projects = [count for section, _, count in self.entries if section == "project"]
        at_experience_minimum = sum(
            count >= minimums.min_experience_bullets for count in experience
        )
        at_project_minimum = sum(count >= minimums.min_project_bullets for count in projects)
        shown = ", ".join(f"{name} ({count})" for _, name, count in self.entries)
        advice: list[str] = []
        if at_experience_minimum and minimums.min_experience_bullets > 1:
            advice.append(
                f"lowering the experience minimum from {minimums.min_experience_bullets} frees "
                f"about {at_experience_minimum} lines per step"
            )
        if at_project_minimum and minimums.min_project_bullets > 1:
            advice.append(
                f"lowering the project minimum from {minimums.min_project_bullets} frees about "
                f"{at_project_minimum} lines per step"
            )
        advice.append(
            "switching off an entry in your profile frees its bullets and about two heading lines"
        )
        return (
            "Even the shortest resume your settings allow runs about "
            f"{self.overflow_lines} printed line{'s' if self.overflow_lines != 1 else ''} past "
            "one page, so no draft was requested and no tokens were spent. With every entry at "
            f"its minimum bullets it prints: {shown}. To win back {self.overflow_lines} lines, "
            + "; ".join(advice)
            + "; then try again."
        )


_cache: OrderedDict[str, PageBudget] = OrderedDict()
_cache_lock = Lock()


def clear_page_budget_cache() -> None:
    with _cache_lock:
        _cache.clear()


def minimal_resume(source: UserResume, minimums: ResumeSettings) -> GeneratedResume:
    experience = [
        item.model_copy(
            update={
                "bullets": [PLACEHOLDER_BULLET]
                * min(minimums.min_experience_bullets, len(item.bullets))
            }
        ).model_dump(exclude={"raw_description", "context", "bullet_context"})
        for item in source.experience
    ]
    floors = [min(minimums.min_project_bullets, len(item.bullets)) for item in source.projects]
    projects = [
        item.model_copy(update={"bullets": [PLACEHOLDER_BULLET] * floor_count}).model_dump(
            exclude={"raw_description", "context", "available_technologies", "bullet_context"}
        )
        for item, floor_count in zip(source.projects, floors, strict=True)
    ]
    skills = compact_skill_lines(
        [
            SkillGroup(category=group.category, items=group.items)
            for group in source.skills
            if group.items
        ]
    )
    return GeneratedResume.model_validate(
        {
            **source.model_dump(mode="json", include=set(ResumeContent.model_fields)),
            "education": [
                item.model_dump(exclude={"available_coursework"}) for item in source.education
            ],
            "experience": experience,
            "projects": projects,
            "skills": [group.model_dump() for group in skills],
            "additional_sections": [item.model_dump() for item in source.additional_sections],
        }
    )


def page_budget(
    source: UserResume, minimums: ResumeSettings, *, compiler: PdfCompiler | None = None
) -> PageBudget:
    document = minimal_resume(source, minimums)
    key = hashlib.sha256(document.model_dump_json(exclude={"ai_usage"}).encode()).hexdigest()
    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None:
            _cache.move_to_end(key)
            return cached
    entries = (
        *(
            (("experience", f"{item.title}, {item.company}", len(item.bullets)))
            for item in document.experience
        ),
        *((("project", item.name, len(item.bullets))) for item in document.projects),
    )
    minimum_lines = sum(count for _, _, count in entries)
    try:
        measured = compile_one_page_measured(resume_to_latex(document), compiler=compiler)
        budget = PageBudget(
            minimum_lines=minimum_lines,
            spare_lines=floor(measured.blank_inches * 72.27 / LINE_POINTS),
            overflow_lines=0,
            entries=entries,
        )
    except DocumentLayoutError as error:
        budget = PageBudget(
            minimum_lines=minimum_lines,
            spare_lines=0,
            overflow_lines=max(1, ceil(error.overflow_points / LINE_POINTS)),
            entries=entries,
        )
    with _cache_lock:
        _cache[key] = budget
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return budget
