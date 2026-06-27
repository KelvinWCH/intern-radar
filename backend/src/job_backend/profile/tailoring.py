from job_backend.resumes.models import ExperienceContext, UserResume


def enabled_entries(profile: UserResume) -> UserResume:
    return profile.model_copy(
        update={
            "education": [entry for entry in profile.education if entry.enabled],
            "skills": [group for group in profile.skills if group.enabled],
            "experience": [entry for entry in profile.experience if entry.enabled],
            "projects": [entry for entry in profile.projects if entry.enabled],
            "additional_sections": [
                section for section in profile.additional_sections if section.enabled
            ],
        }
    )


def tailoring_source(profile: UserResume) -> UserResume:
    source = enabled_entries(profile).model_copy(deep=True)
    for entry in [*source.experience, *source.projects]:
        context = entry.context
        parts = [entry.raw_description]
        for label, value in (
            (
                "Organization mission (background, not a personal achievement)",
                context.company_mission,
            ),
            ("Team purpose (background)", context.team_purpose),
            ("My contribution", context.contribution),
            ("Impact and its scope", context.impact),
            ("Challenges", context.challenges),
            ("What I learned", context.learnings),
        ):
            if value:
                parts.append(f"{label}: {value}")
        if context.tools:
            parts.append("Tools I used: " + ", ".join(context.tools))
        if context.evidence:
            parts.append(
                "Evidence references (do not infer linked contents): " + "\n".join(context.evidence)
            )
        parts.extend(
            f"Context for original bullet {index}: {note}"
            for index, note in enumerate(entry.bullet_context)
            if note
        )
        entry.raw_description = "\n\n".join(parts)
        entry.context = ExperienceContext()
        entry.bullet_context = [None] * len(entry.bullets)
    return source


def candidate_evidence(profile: UserResume) -> str:
    source = tailoring_source(profile)
    return "\n".join(
        [
            *[skill for group in source.skills for skill in group.available_items],
            *[skill for project in source.projects for skill in project.available_technologies],
            *[course for school in source.education for course in school.available_coursework],
            *[
                value
                for entry in [*source.experience, *source.projects]
                for value in [entry.raw_description, *entry.bullets]
            ],
        ]
    )
