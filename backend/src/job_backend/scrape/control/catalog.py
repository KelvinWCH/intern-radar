import sys
from pathlib import Path

from job_backend.scrape.companies.companies import COMPANIES
from job_backend.scrape.control.models import ScrapeRequest, ScrapeSource
from job_backend.scrape.github.github import REPOSITORIES


def list_sources() -> list[ScrapeSource]:
    return [
        *[
            ScrapeSource(
                id=f"github:{key}",
                name=key.replace("-", " "),
                group="github",
                enabled=True,
                source_name=source.name,
            )
            for key, source in REPOSITORIES.items()
        ],
        *[
            ScrapeSource(
                id=f"company:{key}",
                name=company.name,
                group="company",
                enabled=company.supports_scraping,
                source_name=company.source_name if company.supports_scraping else None,
                reason=None
                if company.supports_scraping
                else "A dedicated adapter is not available yet.",
            )
            for key, company in COMPANIES.items()
        ],
    ]


def build_scrape_command(request: ScrapeRequest, database: Path) -> list[str]:
    catalog = {source.id: source for source in list_sources()}
    command = [
        sys.executable,
        "-m",
        "job_backend.cli",
        "--trigger",
        "manual",
        "--state-path",
        str(database),
    ]
    flags = {"github": "--repo", "company": "--company"}
    if request.use_ai:
        command.append("--use-ai")
    for source_id in request.sources:
        source = catalog.get(source_id)
        if source is None or not source.enabled:
            raise ValueError("Select only available sources from the catalog")
        command.extend([flags[source.group], source_id.split(":", 1)[1]])
    return command
