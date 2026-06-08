from collections.abc import Mapping

from job_backend.profile.models import ResumeSettings
from job_backend.resumes.constants import BULLET_GAP_POINTS, LINE_POINTS
from job_backend.resumes.models import GeneratedResume, UserResume


def trim_to_page(
    document: GeneratedResume,
    overflow_points: float,
    bullet_lines: Mapping[str, int],
    minimums: ResumeSettings,
    source: UserResume,
) -> GeneratedResume | None:
    entries = [
        (f"experience-{index}", list(item.bullets), minimums.min_experience_bullets)
        for index, item in enumerate(document.experience)
    ] + [
        (f"project-{index}", list(item.bullets), minimums.min_project_bullets)
        for index, item in enumerate(document.projects)
    ]
    floors = [min(minimum, len(bullets)) for _, bullets, minimum in entries]
    freed = 0.0
    while freed < overflow_points:
        extra = [
            (len(bullets) - floor, position)
            for position, ((_, bullets, _), floor) in enumerate(zip(entries, floors, strict=True))
            if len(bullets) > floor
        ]
        if not extra:
            break
        _, position = max(extra)
        line_id, bullets, _ = entries[position]
        lines = bullet_lines.get(f"{line_id}-{len(bullets) - 1}", 2)
        bullets.pop()
        freed += LINE_POINTS * lines + BULLET_GAP_POINTS
    education = list(document.education)
    for index, school in enumerate(education):
        if freed >= overflow_points:
            break
        defaults = source.education[index].coursework if index < len(source.education) else []
        if school.coursework and not defaults:
            education[index] = school.model_copy(update={"coursework": []})
            freed += LINE_POINTS + BULLET_GAP_POINTS
    if not freed:
        return None
    experience_count = len(document.experience)
    return document.model_copy(
        update={
            "experience": [
                item.model_copy(update={"bullets": entries[index][1]})
                for index, item in enumerate(document.experience)
            ],
            "projects": [
                item.model_copy(update={"bullets": entries[experience_count + index][1]})
                for index, item in enumerate(document.projects)
            ],
            "education": education,
        }
    )
