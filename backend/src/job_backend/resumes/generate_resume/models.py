from typing import Annotated, Literal

from pydantic import Field

from job_backend.common.models import StrictModel
from job_backend.resumes.models import ResumeText

SourceIndex = Annotated[int, Field(ge=0)]


class SupportedBullet(StrictModel):
    """a rewritten or new bullet and the original bullet it replaces, if any"""

    source_bullet: SourceIndex | None = Field(
        description="Zero-based index of the original bullet this rewrites or replaces, or null "
        "for a new bullet drawn from raw_description. Use each original index at most once; "
        "above the entry's minimum, leave out an original bullet that does not help."
    )
    text: ResumeText


class RequirementEvidence(StrictModel):
    """one entry whose own evidence supports a job requirement"""

    section: Literal["experience", "project"]
    source_index: SourceIndex


class RequirementCoverage(StrictModel):
    """map one job requirement to supporting entries before writing bullets"""

    requirement: ResumeText = Field(
        description="One required or preferred qualification or central responsibility, "
        "in the job's own words."
    )
    importance: Literal["required", "preferred"]
    evidence: list[RequirementEvidence] = Field(
        description="Entries whose raw_description or bullets support this requirement, "
        "strongest first. Empty when the profile has no supported evidence; never list an "
        "entry that does not support it."
    )


class EntrySelection(StrictModel):
    """pick one original entry and its strongest supported bullets"""

    source_index: SourceIndex
    bullets: list[SupportedBullet]


class SkillSelection(StrictModel):
    """reorder a categorys defaults and add relevant skills from its inventory"""

    group_index: SourceIndex
    item_indices: list[SourceIndex] = Field(
        description="Indices into this category's available_items, most relevant first. "
        "Every default item stays on the resume: defaults left out are appended in their "
        "saved order. An empty list keeps the defaults unchanged.",
    )


class ProjectTechnologySelection(StrictModel):
    """reorder a projects default stack and add tools saved for it"""

    source_index: SourceIndex
    technology_indices: list[SourceIndex] = Field(
        description="Indices into this project's available_technologies, most relevant first. "
        "Every default technology stays: defaults left out are appended in saved order. "
        "Use an empty list when no change is useful.",
    )


class CourseworkSelection(StrictModel):
    """reorder an education entrys default courses and add relevant saved ones"""

    source_index: SourceIndex
    course_indices: list[SourceIndex] = Field(
        description="Indices into this education entry's available_coursework, most relevant "
        "first. Every default course stays: defaults left out are appended in saved order. "
        "Use an empty list when no change is useful.",
    )


class TailoredContent(StrictModel):
    """pick and tailor evidence without changing the library or the latex"""

    requirement_coverage: list[RequirementCoverage] = Field(
        default_factory=list[RequirementCoverage], max_length=15
    )
    project_technologies: list[ProjectTechnologySelection] = Field(
        default_factory=list[ProjectTechnologySelection]
    )
    education_coursework: list[CourseworkSelection] = Field(
        default_factory=list[CourseworkSelection]
    )
    experience: list[EntrySelection]
    projects: list[EntrySelection]
    skill_selections: list[SkillSelection] = Field(default_factory=list[SkillSelection])
