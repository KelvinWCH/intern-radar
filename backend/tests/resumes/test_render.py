import pytest
from pydantic import ValidationError

from job_backend.resumes.latex import escape_latex
from job_backend.resumes.models import GeneratedResume
from job_backend.resumes.render_latex.render import resume_to_latex
from tests.resumes.helpers import resume


def generated_resume() -> GeneratedResume:
    source = resume()
    return GeneratedResume.model_validate(
        source.model_dump(
            exclude={
                "education": {"__all__": {"available_coursework"}},
                "skills": {"__all__": {"available_items"}},
                "experience": {"__all__": {"raw_description", "context", "bullet_context"}},
                "projects": {
                    "__all__": {
                        "raw_description",
                        "context",
                        "available_technologies",
                        "bullet_context",
                    }
                },
            }
        )
    )


def test_escapes_prose() -> None:
    result = generated_resume()
    result.name = "Zoë Example"
    result.experience[0].bullets = [r"Saved $500 & 25% with C# and a_b {c} ~ ^ \input{secret}"]
    latex = resume_to_latex(result)
    assert "Zoë Example" in latex
    assert r"Saved \$500}{ \& 25\%" in latex
    assert r"C\#" in latex and r"a\_b \{c\}" in latex
    assert r"\textbackslash{}input\{secret\}" in latex
    assert r"\input{secret}" not in latex
    assert "Internal notes" not in latex and "raw_description" not in latex
    assert latex.count(r"\begin{document}") == latex.count(r"\end{document}") == 1
    assert escape_latex("one\n\x00two") == "one  two"


def test_template_sections() -> None:
    result = generated_resume()
    latex = resume_to_latex(result)
    assert r"\documentclass[letterpaper,11pt]{article}" in latex
    assert r"\resumeSubheading" in latex and r"\resumeProjectHeading" in latex
    assert r"\section{Summary}" not in latex
    sections = ["Education", "Experience", "Projects", "Technical Skills"]
    positions = [latex.index(r"\section{" + section + "}") for section in sections]
    assert positions == sorted(positions)
    assert r"\addtolength{\textheight}{1.0in}" in latex and r"\raggedbottom" in latex
    assert r"[\color{black}\titlerule \vspace{-5pt}]" in latex
    assert r"\begin{itemize}[leftmargin=0.15in, label={}]" in latex
    assert r"\textbf{Languages \& tools:} Python, Redis, TypeScript" in latex
    assert "cmunrm.otf" in latex and r"\resumeSmallCaps" in latex
    assert r"\textbf{\Huge Alex Example}" in latex
    with pytest.raises(ValidationError):
        GeneratedResume.model_validate({**result.model_dump(), "summary": "Do not print this"})
    with pytest.raises(ValidationError):
        GeneratedResume.model_validate(
            {
                **result.model_dump(),
                "additional_sections": [
                    {"title": "Professional Summary", "items": ["Do not print this"]}
                ],
            }
        )
