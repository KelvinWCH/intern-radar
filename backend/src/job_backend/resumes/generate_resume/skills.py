import re

from job_backend.common.ai_completion import AiCompletionError
from job_backend.resumes.generate_resume.models import TailoredContent
from job_backend.resumes.models import SkillGroup, UserResume


def keep_defaults(chosen: list[str], defaults: list[str]) -> list[str]:
    return [*chosen, *(item for item in defaults if item not in chosen)]


def tailor_skills(resume: UserResume, content: TailoredContent) -> list[SkillGroup]:
    selected: dict[int, list[int]] = {}
    seen: set[int] = set()
    for selection in content.skill_selections:
        index = selection.group_index
        if index >= len(resume.skills) or index in seen:
            raise AiCompletionError("AI selected an unknown or repeated skill category")
        seen.add(index)
        indices = selection.item_indices
        inventory = resume.skills[index].available_items
        if len(set(indices)) != len(indices) or any(item >= len(inventory) for item in indices):
            raise AiCompletionError("AI selected an unknown or repeated skill inventory item")
        if indices:
            selected[index] = indices

    order = [*selected, *(index for index in range(len(resume.skills)) if index not in selected)]
    groups: list[SkillGroup] = []
    for index in order:
        source = resume.skills[index]
        items = keep_defaults(
            [source.available_items[item] for item in selected.get(index, [])], source.items
        )
        if items:
            groups.append(SkillGroup(category=source.category, items=items))
    return groups


_LANGUAGES = re.compile(r"\blanguages?\b", re.IGNORECASE)
SKILL_LINE_CHARACTERS = 120


def compact_skill_lines(groups: list[SkillGroup]) -> list[SkillGroup]:
    def merged(side: list[SkillGroup], label: str) -> list[SkillGroup]:
        if len(side) < 2:
            return side
        items = list(dict.fromkeys(item for group in side for item in group.items))
        if len(f"{label}: {', '.join(items)}") > SKILL_LINE_CHARACTERS:
            return side
        return [SkillGroup(category=label, items=items)]

    languages = [group for group in groups if _LANGUAGES.search(group.category)]
    others = [group for group in groups if not _LANGUAGES.search(group.category)]
    return [*merged(languages, "Languages"), *merged(others, "Technologies")]
