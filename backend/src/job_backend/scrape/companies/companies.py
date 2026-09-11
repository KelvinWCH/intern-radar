from pathlib import Path

from pydantic import TypeAdapter

from job_backend.scrape.companies.models import Company


def _load_companies() -> dict[str, Company]:
    entries = TypeAdapter(list[Company]).validate_json(
        Path(__file__).with_name("companies.json").read_bytes(), strict=True
    )
    companies: dict[str, Company] = {}
    boards: set[str] = set()
    for company in entries:
        if company.key in companies:
            raise ValueError(f"Duplicate company key: {company.key}")
        if company.supports_scraping:
            if company.source_name in boards:
                raise ValueError(f"Duplicate company board: {company.source_name}")
            boards.add(company.source_name)
        companies[company.key] = company
    return companies


COMPANIES = _load_companies()
