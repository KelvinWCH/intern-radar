import pytest
from pydantic import ValidationError

from job_backend.resumes.models import UserResume
from job_backend.resumes.render_latex.render import resume_to_latex
from tests.resumes.helpers import resume


def with_contact(**fields: object) -> UserResume:
    return UserResume.model_validate({**resume().model_dump(), **fields})


@pytest.mark.parametrize(
    ("field", "value", "stored"),
    [
        (
            "linkedin",
            "https://www.linkedin.com/in/alex-example/",
            "https://www.linkedin.com/in/alex-example",
        ),
        ("github", "@alexexample", "https://github.com/alexexample"),
        ("github", "  ", None),
    ],
)
def test_stores_full_urls(field: str, value: str, stored: str | None) -> None:
    assert getattr(with_contact(**{field: value}), field) == stored


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("linkedin", "https://github.com/alex"),
        ("github", "https://github.com.evil.test/alex"),
        ("github", "https://user:secret@github.com/alex"),
    ],
)
def test_rejects_bad_links(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        with_contact(**{field: value})


def test_header_links() -> None:
    source = with_contact(
        phone="+1 (647) 555-0123",
        linkedin="https://www.linkedin.com/in/alex-example",
        github="alexexample",
        links=[],
    )
    latex = resume_to_latex(source)
    linkedin = (
        r"\href{https://www.linkedin.com/in/alex-example}"
        r"{\underline{linkedin.com/in/alex-example}}"
    )
    github = r"\href{https://github.com/alexexample}{\underline{github.com/alexexample}}"
    assert linkedin in latex and github in latex
    assert latex.index("mailto:") < latex.index(linkedin) < latex.index(github)
