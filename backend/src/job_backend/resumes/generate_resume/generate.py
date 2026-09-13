import json
from collections.abc import Callable, Sequence

import httpx2
from pydantic import JsonValue, ValidationError

from job_backend.common.ai_completion import AiCompletionError, complete_json
from job_backend.common.ai_usage import AiUsageTracker
from job_backend.common.models import AiSettings, AiUsage, CompletionOutput
from job_backend.jobs.models import Job, JobResponse, TailoringJob
from job_backend.persistence.database import Database
from job_backend.profile.models import ResumeSettings, UserProfile
from job_backend.profile.tailoring import tailoring_source
from job_backend.resumes.compile_pdf.compile import DocumentLayoutError
from job_backend.resumes.compile_pdf.models import PdfCompiler
from job_backend.resumes.constants import LINE_POINTS
from job_backend.resumes.database import resume_database
from job_backend.resumes.generate_resume.constants import (
    BULLET_MINIMUMS,
    FILL_FEEDBACK,
    LAYOUT_FEEDBACK,
    LINE_FEEDBACK,
    PAGE_BUDGET,
    SELECTION_FEEDBACK,
    TAILOR_PROMPT,
)
from job_backend.resumes.generate_resume.fit_page import trim_to_page
from job_backend.resumes.generate_resume.models import EntrySelection, TailoredContent
from job_backend.resumes.generate_resume.page_budget import page_budget
from job_backend.resumes.generate_resume.skills import (
    compact_skill_lines,
    keep_defaults,
    tailor_skills,
)
from job_backend.resumes.generation import DraftRevisionRequired, generate_one_page
from job_backend.resumes.models import (
    Experience,
    GeneratedResume,
    ProgressCallback,
    Project,
    ResumeContent,
    UserResume,
)
from job_backend.resumes.progress import report_progress
from job_backend.resumes.review.constants import REVISION_PROMPT
from job_backend.resumes.storage import load_resume
from job_backend.scrape.pipeline.models import ScrapedJob


def generate_resume(
    job: Job | ScrapedJob | JobResponse | TailoringJob,
    *,
    resume: UserResume | None = None,
    engine: Database | None = None,
    settings: AiSettings | None = None,
    transport: httpx2.BaseTransport | None = None,
    compiler: PdfCompiler | None = None,
    on_output: Callable[[CompletionOutput], None] | None = None,
    on_usage: Callable[[AiUsage], None] | None = None,
    instructions: str | None = None,
    on_progress: ProgressCallback | None = None,
    research: dict[str, JsonValue] | None = None,
    on_report: Callable[[dict[str, JsonValue]], None] | None = None,
    review_revision: dict[str, JsonValue] | None = None,
    on_pdf: Callable[[GeneratedResume, bytes], None] | None = None,
    retry_style: bool = True,
    revision_feedback: str = "",
    on_style: Callable[[str], None] | None = None,
    first_draft: TailoredContent | None = None,
) -> GeneratedResume:
    try:
        target = TailoringJob.model_validate(job, from_attributes=True)
    except ValidationError:
        raise ValueError(
            "Tailoring needs a valid job with a nonempty full raw_description"
        ) from None
    if not target.raw_description.strip():
        raise ValueError("Generate a company and role research report before writing documents.")
    if resume is None:
        with resume_database(engine) as database:
            resume = load_resume(database)
    minimums = resume.resume_settings if isinstance(resume, UserProfile) else ResumeSettings()
    resume = tailoring_source(resume)
    config = settings or AiSettings.from_environment()
    usage = AiUsageTracker(config)

    def record_usage(value: AiUsage) -> None:
        usage.record(value)
        if on_usage is not None:
            on_usage(value)

    payload: dict[str, object] = {
        "job": target.metadata() if research is not None else target.model_dump(mode="json"),
        "user_resume": resume.model_dump(
            mode="json", exclude={"stories", "answers", "resume_settings"}
        ),
    }
    if research is not None:
        payload["company_role_research"] = research
    if review_revision is not None:
        payload["review_revision"] = review_revision
    if instructions and instructions.strip():
        payload["candidate_instructions"] = instructions.strip()
    revision_prompt = REVISION_PROMPT if review_revision is not None else ""
    report_progress(on_progress, "prepare", "Preparing saved experience and job description for AI")
    user = json.dumps(payload, ensure_ascii=False)
    if len(user) > config.max_document_chars:
        raise ValueError(
            "Job and user resume exceed JOB_AI_MAX_DOCUMENT_CHARS; no data was truncated"
        )
    source = resume
    report_progress(on_progress, "compile", "Checking that your minimum content fits one page")
    writer_prompt = resume_writer_prompt(source, minimums, compiler=compiler)
    supplied = [first_draft] if first_draft is not None else []

    def make_draft(feedback: str) -> GeneratedResume:
        if supplied:
            selected = supplied.pop()
            report_progress(on_progress, "validate", "Draft received, checking entries and bullets")
        else:
            report_progress(on_progress, "ai", "Sent to the model, waiting for the draft")
            selected = complete_json(
                config,
                system_prompt=writer_prompt + revision_prompt + feedback,
                user_content=user,
                response_model=TailoredContent,
                schema_name="tailored_resume_content",
                transport=transport,
                on_usage=record_usage,
                on_output=on_output,
                on_report=on_report,
            )
            report_progress(
                on_progress, "validate", "Model draft received, checking entries and bullets"
            )
        try:
            _validate_selections(source, selected, minimums)
            return _build_generated_resume(source, selected, on_progress)
        except AiCompletionError as error:
            raise DraftRevisionRequired(
                f"{error}{SELECTION_FEEDBACK}", summary=str(error)
            ) from None
        except ValidationError as error:
            raise AiCompletionError(
                "AI selected content outside the generated resume contract"
            ) from error

    result = generate_one_page(
        make_draft,
        compiler=compiler,
        layout_feedback=LAYOUT_FEEDBACK,
        fill_feedback=FILL_FEEDBACK,
        line_feedback=LINE_FEEDBACK,
        retry_style=retry_style,
        feedback=revision_feedback,
        on_style=on_style,
        on_progress=on_progress,
        on_pdf=on_pdf,
        shorten=lambda document, overflow, lines: trim_to_page(
            document, overflow, lines, minimums, source
        ),
    )
    result.ai_usage = usage.snapshot()
    return result


def resume_writer_prompt(
    source: UserResume,
    minimums: ResumeSettings,
    *,
    compiler: PdfCompiler | None = None,
) -> str:
    minimum_prompt = BULLET_MINIMUMS.format(
        experience=_bullets(minimums.min_experience_bullets),
        project=_bullets(minimums.min_project_bullets),
    )
    budget = page_budget(source, minimums, compiler=compiler)
    if not budget.fits:
        raise DocumentLayoutError(
            budget.blocking_message(minimums), overflow_points=budget.overflow_lines * LINE_POINTS
        )
    budget_prompt = PAGE_BUDGET.format(
        minimum=budget.minimum_lines, spare=budget.spare_lines, allowance=budget.allowance()
    )
    return TAILOR_PROMPT + minimum_prompt + budget_prompt


def _build_generated_resume(
    resume: UserResume,
    content: TailoredContent,
    on_progress: ProgressCallback | None = None,
) -> GeneratedResume:
    skills = compact_skill_lines(tailor_skills(resume, content))

    def entries(
        sources: Sequence[Experience | Project],
        selections: list[EntrySelection],
        *,
        by_relevance: bool = False,
    ) -> list[dict[str, object]]:
        chosen = (
            selections
            if by_relevance
            else sorted(selections, key=lambda selection: selection.source_index)
        )
        return [
            {
                **sources[item.source_index].model_dump(
                    exclude={
                        "raw_description",
                        "context",
                        "available_technologies",
                        "bullet_context",
                    }
                ),
                "bullets": [bullet.text for bullet in item.bullets],
            }
            for item in chosen
        ]

    projects = entries(resume.projects, content.projects, by_relevance=True)
    printed = {item.source_index: position for position, item in enumerate(content.projects)}
    for selection in content.project_technologies:
        if selection.source_index not in printed:
            continue
        source = resume.projects[selection.source_index]
        projects[printed[selection.source_index]]["technologies"] = keep_defaults(
            [source.available_technologies[index] for index in selection.technology_indices],
            source.technologies,
        )
    education = [item.model_dump(exclude={"available_coursework"}) for item in resume.education]
    for selection in content.education_coursework:
        school = resume.education[selection.source_index]
        education[selection.source_index]["coursework"] = keep_defaults(
            [school.available_coursework[index] for index in selection.course_indices],
            school.coursework,
        )

    names = {
        "experience": [f"{item.title}, {item.company}" for item in resume.experience],
        "project": [item.name for item in resume.projects],
    }
    coverage = [
        {
            "requirement": item.requirement,
            "importance": item.importance,
            "entries": list(
                dict.fromkeys(
                    names[evidence.section][evidence.source_index]
                    for evidence in item.evidence
                    if evidence.source_index < len(names[evidence.section])
                )
            ),
        }
        for item in content.requirement_coverage
    ]
    return GeneratedResume.model_validate(
        {
            **resume.model_dump(mode="json", include=set(ResumeContent.model_fields)),
            "requirement_coverage": coverage,
            "education": education,
            "experience": entries(resume.experience, content.experience),
            "projects": projects,
            "skills": [group.model_dump() for group in skills],
            "additional_sections": [item.model_dump() for item in resume.additional_sections],
        }
    )


def _validate_entries(
    section: str,
    sources: Sequence[Experience | Project],
    selections: list[EntrySelection],
    minimum: int,
) -> None:
    indices = [item.source_index for item in selections]
    if len(set(indices)) != len(indices) or any(index >= len(sources) for index in indices):
        raise AiCompletionError("AI selected an unknown or repeated source entry")
    if sorted(indices) != list(range(len(sources))):
        raise AiCompletionError("AI must retain every original experience and project entry")
    for selection in selections:
        entry = sources[selection.source_index]
        originals = [b.source_bullet for b in selection.bullets if b.source_bullet is not None]
        if len(set(originals)) != len(originals) or any(
            index >= len(entry.bullets) for index in originals
        ):
            raise AiCompletionError("AI selected an unknown or repeated source bullet")
        required = min(minimum, len(entry.bullets))
        if len(selection.bullets) < required:
            raise AiCompletionError(
                f"AI must keep at least {_bullets(required)} in {section} entry "
                f"{selection.source_index}"
            )
        if len(selection.bullets) - len(originals) > 2:
            raise AiCompletionError("AI added more than two bullets to one entry")


def _bullets(count: int) -> str:
    return f"{count} bullet" if count == 1 else f"{count} bullets"


def _validate_selections(
    resume: UserResume,
    content: TailoredContent,
    minimums: ResumeSettings,
) -> None:
    if (resume.experience or resume.projects) and not (content.experience or content.projects):
        raise AiCompletionError("AI must select some of the candidate's experience or projects")
    _validate_entries(
        "experience", resume.experience, content.experience, minimums.min_experience_bullets
    )
    _validate_entries("project", resume.projects, content.projects, minimums.min_project_bullets)

    project_indices: set[int] = set()
    for selection in content.project_technologies:
        if (
            selection.source_index >= len(resume.projects)
            or selection.source_index in project_indices
        ):
            raise AiCompletionError("AI selected an unknown or repeated project technology stack")
        project_indices.add(selection.source_index)
        indices = selection.technology_indices
        inventory = resume.projects[selection.source_index].available_technologies
        if len(set(indices)) != len(indices) or any(index >= len(inventory) for index in indices):
            raise AiCompletionError("AI selected an unknown or repeated project technology")

    schools: set[int] = set()
    for selection in content.education_coursework:
        if selection.source_index >= len(resume.education) or selection.source_index in schools:
            raise AiCompletionError("AI selected an unknown or repeated coursework list")
        schools.add(selection.source_index)
        indices = selection.course_indices
        courses = resume.education[selection.source_index].available_coursework
        if len(set(indices)) != len(indices) or any(index >= len(courses) for index in indices):
            raise AiCompletionError("AI selected an unknown or repeated course")
