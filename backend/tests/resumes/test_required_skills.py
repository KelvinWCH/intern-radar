import pytest

from job_backend.profile.required_skills import (
    extract_required_skills,
    matches_skill,
)


@pytest.mark.parametrize(
    "description",
    [
        "Required skills:\nPython and SQL\nPreferred skills:\nRust\nResponsibilities:\nUse Java.",
        "## Minimum qualifications\n- Python\n- SQL\n## Nice to have\n- JavaScript",
        "<h2>What you bring</h2><ul><li><strong>Python</strong> and SQL</li></ul>"
        "<h2>Benefits</h2><p>Free Java courses.</p>",
    ],
)
def test_required_section_only(description: str) -> None:
    assert extract_required_skills(description) == ["Python", "SQL"]


@pytest.mark.parametrize(
    ("skill", "evidence"), [("Java", "JavaScript"), ("SQL", "NoSQL"), ("Go", "Ready to go to work")]
)
def test_no_substring_matches(skill: str, evidence: str) -> None:
    assert not matches_skill(skill, evidence)
