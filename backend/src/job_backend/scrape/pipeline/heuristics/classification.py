import re

from job_backend.common.text_matching import close_spelling, normalized_text
from job_backend.scrape.pipeline.heuristics.constants import (
    CANADIAN_LOCATIONS,
    FOREIGN_LOCATION_PATTERN,
    GTA_LOCATIONS,
    PROVINCE_PATTERN,
)


def _contains(label: str, names: tuple[str, ...]) -> bool:
    words = label.split()
    for name in names:
        size = len(name.split())
        for start in range(len(words) - size + 1):
            part = " ".join(words[start : start + size])
            if part == name or (len(name) >= 6 and close_spelling(part, name)):
                return True
    return False


def classify_locations(locations: list[str]) -> tuple[bool, bool]:
    canada, toronto = False, False
    for location in locations:
        for part in re.split(r"[;|\n]", location):
            label = normalized_text(part)
            if FOREIGN_LOCATION_PATTERN.search(part) or re.search(
                r"\bcalifornia\b|^ontario,\s*ca\b", part, re.I
            ):
                continue
            local_gta = _contains(label, GTA_LOCATIONS)
            toronto |= local_gta
            canada |= (
                local_gta
                or _contains(label, CANADIAN_LOCATIONS)
                or bool(PROVINCE_PATTERN.search(part))
            )
    return canada, toronto


def internship_title(title: str) -> bool:
    label = normalized_text(title)
    if re.search(
        r"\b(internship|intern|student) (?:program )?"
        r"(manager|coordinator|recruiter|recruitment|advisor|adviser|services|affairs)\b",
        label,
    ):
        return False
    if re.search(r"\b(interns?|internships?|co ?op|coop|stagiaire|working student)\b", label):
        return True
    if re.search(r"\bstage\b", label) and not re.search(
        r"\b(?:early|late|preclinical|clinical|commercial|development) stage\b|\bstage [1-4]\b",
        label,
    ):
        return True
    if re.search(
        r"^(?:summer )?(?:undergraduate (?:student )?research(?:er| assistant| fellow| placement)"
        r"|research assistant undergraduate)\b",
        label,
    ):
        return True
    if re.search(
        r"\b(summer|winter|fall|spring)(?: \w+){0,3} (analyst|associate|student)\b", label
    ):
        return True
    if re.search(r"\bstudent\b", label) and not re.search(
        r"\b(student affairs|student services|student advisor|student recruiter)\b", label
    ):
        return True
    return any(close_spelling(word, "internship") for word in label.split())


def role_category(title: str) -> str | None:
    label = normalized_text(title)
    for category, pattern in (
        ("AI & Machine Learning", r"\b(ai|ml|machine learning|deep learning|nlp)\b"),
        ("Data & Analytics", r"\b(data|analytics|business intelligence)\b"),
        ("Security", r"\b(security|cybersecurity|infosec)\b"),
        (
            "Hardware & Engineering",
            r"\b(hardware|firmware|embedded|electrical|mechanical|robotics|fpga|asic|rtl)\b",
        ),
        (
            "Software Engineering",
            r"\b(software|swe|sde|developer|frontend|backend|full stack|devops|"
            r"platform|qa|sdet|test automation|site reliability)\b|"
            r"\b(systems?|network|cloud|infrastructure|quality assurance) engineer(?:ing)?\b",
        ),
        ("Product & Design", r"\b(product|ux|ui|design)\b"),
        (
            "Finance & Business",
            r"\b(finance|financial|banking|investment|analyst|accounting|trading|quantitative)\b",
        ),
        (
            "Research & Science",
            r"\b(research|bioinformatics|computational biology|scientific computing|"
            r"biomedical informatics)\b",
        ),
        ("Hardware & Engineering", r"\bengineering\b"),
    ):
        if re.search(pattern, label):
            return category
    return None
