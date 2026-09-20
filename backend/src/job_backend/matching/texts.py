from job_backend.jobs.descriptions import clean_description
from job_backend.jobs.models import Job
from job_backend.matching.constants import DESCRIPTION_CHARS, SEARCH_CHARS
from job_backend.profile.models import UserProfile


def job_description(job: Job) -> str:
    if job.cleaned_description and job.cleaned_description.strip():
        return job.cleaned_description.strip()
    return (
        clean_description(job.raw_description, source_url=job.source_url or job.application_url)
        or ""
    )


def job_passage(job: Job, description: str) -> str:
    header = "\n".join(
        part
        for part in (
            job.title.strip(),
            job.company.strip(),
            " · ".join(location for location in job.locations if location.strip()),
            " · ".join(term for term in job.terms if term.strip()),
        )
        if part
    )
    body = description[:DESCRIPTION_CHARS]
    return f"{header}\n\n{body}" if body else header


def search_text(job: Job, description: str) -> str:
    return f"{job.title.strip()}\n{description[:SEARCH_CHARS]}"


def graduation_years(job: Job) -> list[int]:
    qualifications = job.qualifications or {}
    education = qualifications.get("education")
    years = education.get("graduation_years") if isinstance(education, dict) else None
    return [year for year in years if isinstance(year, int)] if isinstance(years, list) else []


def profile_skills(profile: UserProfile) -> list[str]:
    found: dict[str, str] = {}
    labels: list[str] = []
    for group in profile.skills:
        if group.enabled:
            labels.extend(group.available_items or group.items)
    for project in profile.projects:
        if project.enabled:
            labels.extend(project.available_technologies or project.technologies)
            labels.extend(project.context.tools)
    for experience in profile.experience:
        if experience.enabled:
            labels.extend(experience.context.tools)
    for label in labels:
        cleaned = " ".join(label.split())
        if cleaned:
            found.setdefault(cleaned.casefold(), cleaned)
    return list(found.values())


def profile_degrees(profile: UserProfile) -> list[str]:
    return [entry.degree for entry in profile.education if entry.enabled and entry.degree]


def role_queries(profile: UserProfile) -> list[str]:
    roles = list(dict.fromkeys(role.strip() for role in profile.preferences.target_roles))
    roles = [role for role in roles if role]
    if roles:
        return roles
    if profile.goals and profile.goals.strip():
        return [profile.goals.strip()[:300]]
    return ["Software engineering internship or co-op"]


def background_query(profile: UserProfile) -> str:
    parts: list[str] = []
    if profile.goals and profile.goals.strip():
        parts.append(profile.goals.strip())
    skills = profile_skills(profile)
    if skills:
        parts.append("Skills: " + ", ".join(skills[:60]))
    for project in profile.projects:
        if project.enabled:
            tools = ", ".join(project.available_technologies or project.technologies)
            parts.append(f"Project: {project.name}" + (f" ({tools})" if tools else ""))
    for experience in profile.experience:
        if experience.enabled:
            parts.append(f"Experience: {experience.title} at {experience.company}")
    return "\n".join(parts)[:2000]
