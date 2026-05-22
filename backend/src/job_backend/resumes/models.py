from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, ClassVar, Literal, Self

from pydantic import BaseModel, Field, JsonValue, ValidationInfo, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

from job_backend.common.constants import MAX_CONSOLE_OUTPUT_CHARS
from job_backend.common.models import AiUsage, StrictModel
from job_backend.persistence.models import StoredRecord
from job_backend.resumes.profile_links import (
    ProfileSite,
    normalize_profile_label,
    normalize_profile_url,
    split_profile_links,
)
from job_backend.scrape.pipeline.models import Qualifications


class PreviousFinding(StrictModel):
    """link a recurring issue to a finding from an earlier review round"""

    round: int = Field(ge=1)
    finding_index: int = Field(ge=0)


class ReviewFinding(StrictModel):
    """a concrete problem in a draft, without editing it"""

    document: Literal["resume", "cover_letter", "both"]
    category: Literal["grounding", "consistency", "requirements", "writing"]
    severity: Literal["error", "warning", "suggestion"]
    draft_quote: str = Field(max_length=4000)
    issue: str = Field(min_length=1, max_length=4000)
    recommendation: str = Field(min_length=1, max_length=4000)
    previous_finding: PreviousFinding | None = None


class ResumeGap(StrictModel):
    """a job requirement the resume doesnt show, and why"""

    requirement: str = Field(min_length=1, max_length=1000)
    importance: Literal["required", "preferred"]
    status: Literal["not_shown", "no_evidence"] = Field(
        description="not_shown: the profile supports it but the resume omits or buries it. "
        "no_evidence: the profile has no supporting evidence."
    )
    detail: str = Field(min_length=1, max_length=2000)


class ReviewAnalysis(StrictModel):
    """actionable critique, not a made up score"""

    summary: str = Field(min_length=1, max_length=4000)
    gaps: list[ResumeGap] = Field(default_factory=list[ResumeGap], max_length=20)
    findings: list[ReviewFinding] = Field(max_length=30)


class ReviewPass(StrictModel):
    round: int = Field(ge=1)
    analysis: ReviewAnalysis
    document_hashes: dict[str, str]
    ai_usage: AiUsage
    acknowledged_finding_indices: list[Annotated[int, Field(ge=0)]] = Field(
        default_factory=list[int], max_length=30
    )

    @model_validator(mode="after")
    def validate_acknowledged_findings(self) -> Self:
        indices = self.acknowledged_finding_indices
        if len(set(indices)) != len(indices) or any(
            index >= len(self.analysis.findings)
            or self.analysis.findings[index].severity == "suggestion"
            for index in indices
        ):
            raise ValueError("Acknowledged findings must identify distinct material findings")
        return self


class FindingDecision(StrictModel):
    finding_index: int = Field(ge=0)
    action: Literal["keep", "revise"]
    guidance: str = Field(default="", max_length=2000)


class ReviewDecision(StrictModel):
    round: int = Field(ge=1)
    decisions: list[FindingDecision] = Field(min_length=1, max_length=30)


class ApplicationReview(StrictModel):
    passes: list[ReviewPass] = Field(default_factory=list[ReviewPass])
    decisions: list[ReviewDecision] = Field(default_factory=list[ReviewDecision])
    revised_documents: list[Literal["resume", "cover_letter"]] = Field(
        default_factory=list[Literal["resume", "cover_letter"]], max_length=2
    )
    status: Literal[
        "reviewing", "revising", "awaiting_decision", "completed", "needs_attention", "failed"
    ] = "reviewing"


class BulletLayout(StrictModel):
    section: Literal["experience", "projects"]
    entry: int = Field(ge=0)
    bullet: int = Field(ge=0)
    lines: int = Field(ge=1, le=3, description="Printed lines; 3 means past about 1.9 lines.")
    issue: Literal["wrapped", "dangling", "late", "short"] | None = Field(
        default=None,
        description="wrapped: runs past two lines; dangling: only a few words on its second "
        "line; late: its first number prints after the first line; short: uses under 80% of "
        "its one line.",
    )
    characters: int = Field(
        default=0,
        ge=0,
        description="About how many characters to cut (wrapped, dangling, late) or that would "
        "still fit (short); zero without an issue.",
    )


class FittedLine(StrictModel):
    section: Literal["projects", "education"]
    entry: int = Field(ge=0)
    printed: int = Field(ge=0)


class DraftPreview(StrictModel):
    pdf_base64: str = Field(description="The compiled PDF, base64-encoded.")
    page_count: int = Field(ge=1)
    overflow_lines: int = Field(ge=0, description="Printed lines past one page; zero when it fits.")
    blank_inches: float = Field(
        ge=0, description="Blank space below the last line of a one-page draft, when measured."
    )
    bullets: list[BulletLayout]
    fitted: list[FittedLine]


ResumeText = Annotated[str, Field(min_length=1, pattern=r"\S")]
LINKEDIN_DESCRIPTION = (
    "Full LinkedIn profile URL, or null. When a PDF shows only the word LinkedIn, use its "
    "hyperlink target from the supplied link list; never guess a URL."
)
LINKEDIN_LABEL_DESCRIPTION = (
    "Always null; the candidate sets custom header text for the LinkedIn link themselves."
)
GITHUB_DESCRIPTION = (
    "Full GitHub profile URL (github.com/username), or null. When a PDF shows only the word "
    "GitHub, use its hyperlink target from the supplied link list; never guess a URL."
)
ResumeBullets = Annotated[
    list[ResumeText],
    Field(
        description="Ordered bullet points, with one complete bullet per array item. "
        "Use an empty array when there are no bullets; never join bullets into a single string."
    ),
]


class SkillGroup(StrictModel):
    category: ResumeText
    items: list[ResumeText] = Field(min_length=1)


class Education(StrictModel):
    institution: ResumeText
    degree: str | None
    field_of_study: str | None
    location: str | None
    start_date: str | None
    end_date: str | None
    bullets: ResumeBullets
    coursework: list[ResumeText] = Field(
        default_factory=list[ResumeText],
        description="Courses printed on one Relevant Coursework line, most relevant first.",
    )


class ResumeExperience(StrictModel):
    company: ResumeText
    title: ResumeText
    location: str | None
    start_date: str | None
    end_date: str | None
    bullets: ResumeBullets


class ResumeProject(StrictModel):
    name: ResumeText
    url: str | None
    technologies: list[ResumeText]
    start_date: str | None
    end_date: str | None
    bullets: ResumeBullets


class ResumeSection(StrictModel):
    title: ResumeText
    items: list[ResumeText] = Field(min_length=1)


class ResumeContent(StrictModel):
    name: ResumeText
    email: str | None
    phone: str | None
    location: str | None
    linkedin: str | None = Field(default=None, description=LINKEDIN_DESCRIPTION)
    linkedin_label: str | None = Field(default=None, description=LINKEDIN_LABEL_DESCRIPTION)
    github: str | None = Field(default=None, description=GITHUB_DESCRIPTION)
    links: list[ResumeText] = Field(
        description="Other contact links such as a portfolio. LinkedIn and GitHub profiles "
        "belong in their own fields."
    )

    @field_validator("linkedin", "github", mode="before")
    @classmethod
    def normalize_profiles(cls, value: object, info: ValidationInfo) -> object:
        site: ProfileSite = "linkedin" if info.field_name == "linkedin" else "github"
        return normalize_profile_url(site, value)

    @field_validator("linkedin_label", mode="before")
    @classmethod
    def normalize_label(cls, value: object) -> object:
        return normalize_profile_label(value)

    @model_validator(mode="after")
    def move_profile_links(self) -> Self:
        self.links, self.linkedin, self.github = split_profile_links(
            self.links, self.linkedin, self.github
        )
        return self


class ModelCatalog(StrictModel):
    models: list[str]
    warning: str | None = None


class ProviderModel(BaseModel):
    id: str = Field(min_length=1, max_length=200)


class ProviderModelCatalog(BaseModel):
    data: list[ProviderModel] = Field(max_length=10000)


class PdfDiagnosticCheck(StrictModel):
    key: str
    label: str
    status: Literal["passed", "warning", "info"]
    detail: str
    missing: list[str] = Field(default_factory=list[str])


class PdfDiagnostics(StrictModel):
    document: Literal["resume", "cover_letter"]
    document_sha256: str
    pdf_sha256: str
    page_count: int
    extracted_text: str
    checks: list[PdfDiagnosticCheck]
    matched_required_skills: list[str]
    missing_supported_skills: list[str]
    unsupported_required_skills: list[str]
    matched_keywords: list[str] = Field(default_factory=list[str])
    missing_supported_keywords: list[str] = Field(default_factory=list[str])
    unsupported_keywords: list[str] = Field(default_factory=list[str])


MAX_KEYWORDS = 25


class ResearchSource(StrictModel):
    title: str
    url: str | None
    text: str


class ResearchFinding(StrictModel):
    """a research claim tied to an exact quote from one source"""

    finding: str = Field(min_length=1)
    source_index: int = Field(ge=0)
    quote: str


class ResearchAnalysis(StrictModel):
    """employer context kept separate from role requirements and unknowns"""

    mission: ResearchFinding | None
    company_context: list[ResearchFinding]
    company_knowledge: list[str] = Field(
        default_factory=list[str],
        max_length=10,
        description="What you know about the company from your own knowledge rather than the "
        "sources: mission, products, users, goals, and recent direction, one fact per item. "
        "Unverified and possibly outdated; empty when you do not know the company.",
    )
    role_priorities: list[ResearchFinding]
    requirements: list[ResearchFinding] = Field(
        description="Required qualifications only; preferred ones go in preferred_qualifications."
    )
    preferred_qualifications: list[ResearchFinding] = Field(
        default_factory=list[ResearchFinding],
        description="Preferred, bonus, or nice-to-have qualifications.",
    )
    keywords: list[str] = Field(
        default_factory=list[str],
        max_length=MAX_KEYWORDS,
        description="The posting's exact search terms: languages, tools, frameworks, methods, "
        "and domain terms a recruiter or applicant tracking system would match, most "
        "important first.",
    )
    tailoring_guidance: list[str]
    unknowns: list[str]
    general_role_guidance: list[str] = Field(default_factory=list[str])


class ResearchSourcePlan(StrictModel):
    """public employer pages worth reading, not evidence until fetched"""

    urls: list[str] = Field(max_length=3)


class ResearchReport(StrictModel):
    analysis: ResearchAnalysis
    sources: list[ResearchSource]
    warnings: list[str]
    ai_usage: AiUsage
    validated: bool = False
    system_prompt: str = ""
    validation_issues: list[str] = Field(default_factory=list[str])
    revision: int = Field(default=1, ge=1)
    approved_at: int | None = None
    mode: Literal["job_description", "generic"] = "job_description"
    research_prompt: str = ""
    qualifications: Qualifications | None = None


class ResearchReview(StrictModel):
    revision: int = Field(ge=1)
    action: Literal["save", "continue", "generate_generic"]
    analysis: ResearchAnalysis | None = None
    research_prompt: str | None = Field(default=None, max_length=2000)


class TailoringStage(StrictModel):
    key: Literal["research", "resume", "cover_letter", "reviewer", "pdf_diagnostics"]
    label: str
    model: str
    status: Literal[
        "queued", "running", "awaiting_review", "completed", "failed", "skipped", "cancelled"
    ]
    message: str


class GenerationReport(StrictModel):
    stage: Literal["research", "resume", "cover_letter", "reviewer"]
    attempt: int
    created_at: int
    content: dict[str, JsonValue]


@dataclass(kw_only=True)
class ResumeRecord(StoredRecord):
    collection: ClassVar[str] = "user_profile"
    key_fields: ClassVar[tuple[str, ...]] = ("id",)
    id: int = 1
    data: dict[str, JsonValue] = field(default_factory=dict[str, JsonValue])
    updated_at: int = 0
    revision: int = 1


GenerationStage = Literal[
    "queued",
    "prepare",
    "ai",
    "output",
    "validate",
    "compile",
    "retry",
    "save",
    "done",
    "error",
    "paused",
    "resumed",
    "cancelled",
]

ProgressCallback = Callable[[GenerationStage, str], None]


class TailoringEvent(StrictModel):
    id: int = Field(ge=1)
    created_at: int = Field(ge=0)
    stage: GenerationStage
    message: str = Field(min_length=1, max_length=500)
    details: str | None = None
    output: str | None = Field(default=None, max_length=MAX_CONSOLE_OUTPUT_CHARS)
    reasoning: str | None = Field(default=None, max_length=MAX_CONSOLE_OUTPUT_CHARS)
    output_schema: str | None = Field(default=None, max_length=100)


class GeneratedCoverLetter(StrictModel):
    name: ResumeText
    email: str | None
    phone: str | None
    location: str | None
    linkedin: str | None = None
    linkedin_label: str | None = None
    github: str | None = None
    links: list[ResumeText]
    company: ResumeText
    job_title: ResumeText
    greeting: Literal["Dear Hiring Manager,"]
    paragraphs: list[ResumeText] = Field(min_length=3, max_length=4)
    closing: Literal["Sincerely,"]
    ai_usage: AiUsage | None = None

    @field_validator("linkedin", "github", mode="before")
    @classmethod
    def normalize_profiles(cls, value: object, info: ValidationInfo) -> object:
        site: ProfileSite = "linkedin" if info.field_name == "linkedin" else "github"
        return normalize_profile_url(site, value)

    @field_validator("linkedin_label", mode="before")
    @classmethod
    def normalize_label(cls, value: object) -> object:
        return normalize_profile_label(value)

    @model_validator(mode="after")
    def move_profile_links(self) -> Self:
        self.links, self.linkedin, self.github = split_profile_links(
            self.links, self.linkedin, self.github
        )
        return self

    @model_validator(mode="after")
    def validate_paragraphs(self) -> Self:
        normalized = [" ".join(paragraph.split()) for paragraph in self.paragraphs]
        if len(set(normalized)) != len(normalized):
            raise ValueError("Cover-letter paragraphs must be distinct")
        if sum(len(paragraph.split()) for paragraph in self.paragraphs) > 450:
            raise ValueError("Cover-letter body must contain at most 450 words")
        return self


class RequirementMatch(StrictModel):
    requirement: str
    importance: Literal["required", "preferred"]
    entries: list[str] = Field(
        default_factory=list[str],
        description="Experience titles and project names showing it; empty for a gap.",
    )


class GeneratedResume(ResumeContent):
    education: list[Education]
    skills: list[SkillGroup]
    experience: list[ResumeExperience]
    projects: list[ResumeProject]
    additional_sections: list[ResumeSection]
    ai_usage: AiUsage | None = None
    requirement_coverage: list[RequirementMatch] = Field(default_factory=list[RequirementMatch])

    @field_validator("additional_sections")
    @classmethod
    def reject_summary_sections(cls, sections: list[ResumeSection]) -> list[ResumeSection]:
        prohibited = {
            "summary",
            "professional summary",
            "career summary",
            "profile",
            "about me",
            "objective",
            "career objective",
            "professional profile",
            "executive summary",
        }
        if any(" ".join(section.title.lower().split()) in prohibited for section in sections):
            raise ValueError("Generated resumes do not include a summary or objective section")
        return sections


class ExperienceContext(StrictModel):
    """detailed evidence kept next to the short resume version of an entry"""

    company_mission: str | None = Field(default=None, max_length=10000)
    team_purpose: str | None = Field(default=None, max_length=10000)
    contribution: str | None = Field(default=None, max_length=20000)
    impact: str | None = Field(default=None, max_length=20000)
    challenges: str | None = Field(default=None, max_length=10000)
    learnings: str | None = Field(default=None, max_length=10000)
    tools: list[str] = Field(default_factory=list, max_length=100)
    evidence: list[str] = Field(default_factory=list, max_length=100)


EntryEnabled = Annotated[
    SkipJsonSchema[bool],
    Field(
        description="False keeps the entry saved but leaves it out of every resume, cover "
        "letter, and answer until it is switched back on.",
        exclude_if=lambda enabled: enabled is True,
    ),
]


class SourceSkillGroup(StrictModel):
    """a categorys full skill inventory, separate from the ordered resume defaults"""

    category: ResumeText
    items: list[ResumeText]
    enabled: EntryEnabled = True
    available_items: list[ResumeText] = Field(
        default_factory=list[ResumeText],
        description="All candidate-supplied skills in this category. items is the ordered "
        "default subset shown on the untailored resume, and may be empty.",
    )

    @model_validator(mode="after")
    def validate_skill_inventory(self) -> Self:
        if "available_items" not in self.model_fields_set:
            self.available_items = list(self.items)
        inventory = [item.strip().casefold() for item in self.available_items]
        defaults = [item.strip().casefold() for item in self.items]
        if len(set(inventory)) != len(inventory) or len(set(defaults)) != len(defaults):
            raise ValueError("Skills must be unique within a category")
        if any(item not in inventory for item in defaults):
            raise ValueError("Default skills must belong to the category's inventory")
        labels = {item.strip().casefold(): item for item in self.available_items}
        self.items = [labels[item] for item in defaults]
        return self


class SourceEducation(Education):
    """every course taken here, separate from the ordered default selection"""

    enabled: EntryEnabled = True
    available_coursework: list[ResumeText] = Field(
        default_factory=list[ResumeText],
        description="Every course the candidate took here. coursework is the ordered default "
        "subset shown on the untailored resume, and may be empty.",
    )

    @model_validator(mode="after")
    def validate_coursework_inventory(self) -> Self:
        if "available_coursework" not in self.model_fields_set:
            self.available_coursework = list(self.coursework)
        inventory = [item.strip().casefold() for item in self.available_coursework]
        defaults = [item.strip().casefold() for item in self.coursework]
        if len(set(inventory)) != len(inventory) or len(set(defaults)) != len(defaults):
            raise ValueError("Courses must be unique within an education entry")
        if any(item not in inventory for item in defaults):
            raise ValueError("Default courses must belong to the education entry's inventory")
        labels = {item.strip().casefold(): item for item in self.available_coursework}
        self.coursework = [labels[item] for item in defaults]
        return self


BULLET_CONTEXT_DESCRIPTION = (
    "Optional private notes for each display bullet, aligned by index: numbers, how they were "
    "measured, who used the work, and why it mattered. Never printed; tailoring evidence only. "
    "Use null for a bullet without notes, or an empty array when no bullet has any."
)


def align_bullet_context(context: list[str | None], bullets: list[str]) -> list[str | None]:
    notes = [(note or "").strip() or None for note in context]
    if any(notes[len(bullets) :]):
        raise ValueError("Each bullet context must belong to a display bullet")
    return [*notes[: len(bullets)], *([None] * (len(bullets) - len(notes)))]


class Experience(ResumeExperience):
    """display bullets plus all the details of a work experience"""

    raw_description: ResumeText = Field(
        title="Context data for tailoring",
        description="All supplied details about this experience, including responsibilities, "
        "tools, accomplishments, metrics, and context omitted from display bullets. "
        "Preserve the source details without summarizing or inventing them.",
    )
    enabled: EntryEnabled = True
    context: ExperienceContext = Field(default_factory=ExperienceContext)
    bullet_context: list[str | None] = Field(
        default_factory=list[str | None], description=BULLET_CONTEXT_DESCRIPTION
    )

    @model_validator(mode="after")
    def validate_bullet_context(self) -> Self:
        self.bullet_context = align_bullet_context(self.bullet_context, self.bullets)
        return self


class Project(ResumeProject):
    """project highlights plus fuller material for later generation"""

    available_technologies: list[ResumeText] = Field(
        default_factory=list,
        description="Complete inventory of technologies actually used in this project. "
        "technologies is the ordered default subset shown on the untailored resume.",
    )

    @model_validator(mode="after")
    def validate_technology_inventory(self) -> Self:
        if "available_technologies" not in self.model_fields_set:
            self.available_technologies = list(self.technologies)
        inventory = [item.strip().casefold() for item in self.available_technologies]
        defaults = [item.strip().casefold() for item in self.technologies]
        if len(set(inventory)) != len(inventory) or len(set(defaults)) != len(defaults):
            raise ValueError("Project technologies must be unique")
        if any(item not in inventory for item in defaults):
            raise ValueError("Default technologies must belong to the project's inventory")
        labels = {item.strip().casefold(): item for item in self.available_technologies}
        self.technologies = [labels[item] for item in defaults]
        return self

    raw_description: ResumeText = Field(
        title="Context data for tailoring",
        description="All supplied project details, including architecture, contribution, tools, "
        "results, and context omitted from display bullets. Preserve rather than summarize.",
    )
    enabled: EntryEnabled = True
    context: ExperienceContext = Field(default_factory=ExperienceContext)
    bullet_context: list[str | None] = Field(
        default_factory=list[str | None], description=BULLET_CONTEXT_DESCRIPTION
    )

    @model_validator(mode="after")
    def validate_bullet_context(self) -> Self:
        self.bullet_context = align_bullet_context(self.bullet_context, self.bullets)
        return self


class SourceSection(ResumeSection):
    """an extra section that can be switched off without deleting it"""

    enabled: EntryEnabled = True


class UserResume(ResumeContent):
    """candidate facts, including longer descriptions that dont fit on a short resume.

    missing values are null and missing lists are empty. dates keep their original wording.
    raw descriptions hold candidate facts, never target job requirements
    """

    education: list[SourceEducation]
    skills: list[SourceSkillGroup]
    experience: list[Experience]
    projects: list[Project]
    additional_sections: list[SourceSection]


class UnfittedResume(StrictModel):
    document: GeneratedResume
    overflow_lines: int = Field(ge=0)


class UnfittedCoverLetter(StrictModel):
    document: GeneratedCoverLetter
    overflow_lines: int = Field(ge=0)
