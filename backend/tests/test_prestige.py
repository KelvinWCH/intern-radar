import pytest

from job_backend.jobs.company_priority import prestige_priority


@pytest.mark.parametrize("company", ["Microsoft Corporation", "1 Password", "Shopfy"])
def test_recognizable_names_and_variants(company: str) -> None:
    assert prestige_priority(company) == 1


@pytest.mark.parametrize("company", ["Unknown Startup", "Apple Orchard", "TDD"])
def test_no_substring_matching(company: str) -> None:
    assert prestige_priority(company) == 0
