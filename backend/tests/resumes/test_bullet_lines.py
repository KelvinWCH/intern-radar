from job_backend.resumes.render_latex.render import resume_to_latex
from tests.resumes.test_render import generated_resume

WRAP = "JOB-RESUME-WRAP: experience-0-0 41.0pt"
DANGLE = "JOB-RESUME-DANGLE: experience-0-0 20.5pt"
LATE = "JOB-RESUME-LATE: experience-0-0 82.0pt"


def test_bullet_line_measure() -> None:
    latex = resume_to_latex(generated_resume())
    assert r"\resumeLineItem{experience-0-0}{" in latex
    assert r"\resumeLineItem{project-0-0}{" in latex
    for kind in ["WRAP", "DANGLE", "LATE", "SHORT"]:
        assert f"JOB-RESUME-{kind}" in latex
