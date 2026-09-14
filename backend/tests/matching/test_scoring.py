from dataclasses import replace

import numpy as np

from job_backend.matching.scoring import (
    JobFacts,
    ScoredJob,
    band_for,
    calibrate,
    degree_gap,
    location_part,
    quantiles,
    score_job,
    skills_part,
)

BASE = JobFacts(
    job_id="job-1",
    content_hash="a",
    title="Software Engineering Intern",
    locations=["Toronto, ON, Canada"],
    is_canada_internship=True,
    is_toronto_area=True,
)


def _facts(**fields: object) -> JobFacts:
    return replace(BASE, **fields)


def _result(
    facts: JobFacts,
    *,
    feedback: float | None = None,
    positives: int = 0,
    role_label: str | None = "Software Engineering Intern",
    graduation_year: int | None = 2028,
) -> ScoredJob:
    return score_job(
        facts,
        role=0.95,
        role_label=role_label,
        background=0.95,
        feedback=feedback,
        positives=positives,
        idf={"Python": 1.0, "PyTorch": 4.0},
        preferred_locations=["Toronto, ON"],
        graduation_year=graduation_year,
    )


def _score(facts: JobFacts, *, feedback: float | None = None, positives: int = 0) -> int:
    return _result(facts, feedback=feedback, positives=positives).score


def test_preferred_city_ranks_first() -> None:
    assert location_part(["Toronto, ON"], True, ["Toronto, ON"]) == (1.0, "In Toronto")
    assert location_part(["Mississauga, ON"], True, ["Toronto, ON"])[1] == "Toronto area"
    assert location_part(["Vancouver, BC, Canada"], False, ["Toronto, ON"])[0] == 0.6
    assert location_part(["Seattle, WA, USA"], False, ["Toronto, ON"]) == (0.1, "Outside Canada")
    assert location_part([], None, ["Toronto, ON"]) == (0.5, None)
    assert location_part(["Torontonian Hall, Calgary, AB, Canada"], False, ["Toronto"])[0] == 0.6


def test_rare_skills_weigh_more() -> None:
    rare, ranked = skills_part({"Python", "PyTorch"}, {"Python": 1.0, "PyTorch": 4.0})
    common, _ = skills_part({"Python"}, {"Python": 1.0, "PyTorch": 4.0})
    assert ranked == ["PyTorch", "Python"]
    assert 0 < common < rare < 1


def test_non_student_roles_demoted() -> None:
    student = _score(_facts(skills={"PyTorch"}))
    full_time = _result(_facts(title="Senior Engineer", is_canada_internship=False))
    phd = _result(_facts(title="PhD Research Intern", degree_gap="PhD"))
    assert full_time.score < student
    assert "Not a student role" in full_time.reasons
    assert "For PhD students" in phd.reasons and phd.components["eligibility"] == 0.0
    assert degree_gap("PhD Research Intern", ["BSc"]) == "PhD"
    assert degree_gap("Research Intern, Master's", ["Bachelor of Science"]) == "master's"
    assert degree_gap("PhD Research Intern", ["PhD, Computer Science"]) is None
    assert degree_gap("Software Engineering Intern", ["BSc"]) is None


def test_feedback_changes_scores() -> None:
    without = _score(_facts(), feedback=None)
    liked = _score(_facts(), feedback=1.0, positives=6)
    disliked = _score(_facts(), feedback=0.0, positives=6)
    assert disliked < without < liked


def test_bands_and_calibration() -> None:
    assert [band_for(score) for score in (85, 75, 60, 10)] == ["strong", "good", "fair", "low"]
    points = quantiles(np.linspace(0.2, 0.8, 1000, dtype=np.float32))
    mapped = calibrate(np.asarray([0.1, 0.5, 0.9], dtype=np.float32), points)
    assert mapped[0] == 0.0 and abs(mapped[1] - 0.5) < 0.01 and mapped[2] == 1.0
    flat = calibrate(np.asarray([0.3], dtype=np.float32), quantiles(np.full(10, 0.3, np.float32)))
    assert 0.0 <= flat[0] <= 1.0
    assert calibrate(np.asarray([0.3], dtype=np.float32), [])[0] == 0.5
