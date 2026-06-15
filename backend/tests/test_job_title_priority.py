import pytest

from job_backend.jobs.title_priority import engineering_title_priority


@pytest.mark.parametrize("title", ["Software Developer Intern", "SWE Intern", "sde co-op"])
def test_explicit_engineering_titles(title: str) -> None:
    assert engineering_title_priority(title) == 0
