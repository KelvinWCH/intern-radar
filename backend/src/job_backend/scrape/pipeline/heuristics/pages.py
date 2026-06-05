from urllib.parse import urlsplit

from job_backend.scrape.ashby.constants import PAGE_HOSTS as ASHBY_HOSTS
from job_backend.scrape.ashby.page import extract_page as ashby_page
from job_backend.scrape.avature.page import extract_page as avature_page
from job_backend.scrape.avature.page import page_hosts as avature_hosts
from job_backend.scrape.dayforce.constants import DESCRIPTION_SELECTOR as DAYFORCE_DESCRIPTION
from job_backend.scrape.dayforce.constants import PAGE_HOSTS as DAYFORCE_HOSTS
from job_backend.scrape.dayforce.page import extract_page as dayforce_page
from job_backend.scrape.eightfold.constants import PAGE_HOSTS as EIGHTFOLD_HOSTS
from job_backend.scrape.eightfold.page import extract_page as eightfold_page
from job_backend.scrape.greenhouse.constants import PAGE_HOSTS as GREENHOUSE_HOSTS
from job_backend.scrape.greenhouse.page import extract_page as greenhouse_page
from job_backend.scrape.lever.constants import PAGE_HOSTS as LEVER_HOSTS
from job_backend.scrape.lever.page import extract_page as lever_page
from job_backend.scrape.pipeline.heuristics.markup import PageMarkup
from job_backend.scrape.pipeline.heuristics.models import PageFacts
from job_backend.scrape.rippling.constants import PAGE_HOSTS as RIPPLING_HOSTS
from job_backend.scrape.rippling.page import extract_page as rippling_page
from job_backend.scrape.successfactors.page import extract_page as successfactors_page
from job_backend.scrape.successfactors.page import page_hosts as successfactors_hosts
from job_backend.scrape.workable.constants import PAGE_HOSTS as WORKABLE_HOSTS
from job_backend.scrape.workable.page import extract_page as workable_page
from job_backend.scrape.workday.constants import PAGE_HOST_SUFFIX as WORKDAY_SUFFIX
from job_backend.scrape.workday.page import extract_page as workday_page


def description_selector(source_url: str) -> str | None:
    host = urlsplit(source_url).hostname or ""
    if host in DAYFORCE_HOSTS:
        return DAYFORCE_DESCRIPTION
    return None


def provider_page(markup: PageMarkup, source_url: str) -> PageFacts:
    host = urlsplit(source_url).hostname or ""
    for hosts, extract in (
        (GREENHOUSE_HOSTS, greenhouse_page),
        (LEVER_HOSTS, lever_page),
        (ASHBY_HOSTS, ashby_page),
        (WORKABLE_HOSTS, workable_page),
        (EIGHTFOLD_HOSTS, eightfold_page),
        (DAYFORCE_HOSTS, dayforce_page),
        (RIPPLING_HOSTS, rippling_page),
    ):
        if host in hosts:
            return extract(markup, source_url)
    if host.endswith(WORKDAY_SUFFIX):
        return workday_page(markup, source_url)
    if host in successfactors_hosts():
        return successfactors_page(markup, source_url)
    if host in avature_hosts():
        return avature_page(markup, source_url)
    return PageFacts()
