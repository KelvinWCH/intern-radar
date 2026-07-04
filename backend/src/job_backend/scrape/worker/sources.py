from job_backend.scrape.companies.companies import COMPANIES
from job_backend.scrape.companies.company_sources import COMPANY_SOURCES
from job_backend.scrape.github.github import REPOSITORIES
from job_backend.scrape.worker.constants import API_BOARDS
from job_backend.scrape.worker.models import ScheduledScrape, SourceGroup, WorkerSettings


def group_sources(group: SourceGroup) -> list[tuple[str, str]]:
    if group == "github":
        return [(key, source.name) for key, source in REPOSITORIES.items()]
    return [
        (key, source.name)
        for key, source in COMPANY_SOURCES.items()
        if (COMPANIES[key].job_board in API_BOARDS) == (group == "boards")
    ]


def scheduled_sources(settings: WorkerSettings) -> dict[str, ScheduledScrape]:
    return {
        name: task
        for task in settings.tasks
        if task.enabled
        for _key, name in group_sources(task.group)
    }
