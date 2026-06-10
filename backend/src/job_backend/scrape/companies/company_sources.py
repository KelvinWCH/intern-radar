from job_backend.scrape.ashby.ashby import create_source as ashby_source
from job_backend.scrape.avature.avature import create_source as avature_source
from job_backend.scrape.companies.companies import COMPANIES
from job_backend.scrape.employmenthero.employmenthero import create_source as employmenthero_source
from job_backend.scrape.greenhouse.greenhouse import create_source as greenhouse_source
from job_backend.scrape.hibob.hibob import create_source as hibob_source
from job_backend.scrape.lever.lever import create_source as lever_source
from job_backend.scrape.oracle.oracle import create_source as oracle_source
from job_backend.scrape.pipeline.models import JobSource
from job_backend.scrape.recruitee.recruitee import create_source as recruitee_source
from job_backend.scrape.smartrecruiters.smartrecruiters import (
    create_source as smartrecruiters_source,
)
from job_backend.scrape.successfactors.successfactors import (
    create_source as successfactors_source,
)
from job_backend.scrape.workable.workable import create_source as workable_source
from job_backend.scrape.workday.workday import create_source as workday_source


def _company_sources() -> dict[str, JobSource]:
    sources: dict[str, JobSource] = {}
    for key, company in COMPANIES.items():
        if company.job_board == "lever":
            sources[key] = lever_source(company)
        elif company.job_board == "greenhouse":
            sources[key] = greenhouse_source(company)
        elif company.job_board == "ashby":
            sources[key] = ashby_source(company)
        elif company.job_board == "workday":
            sources[key] = workday_source(company)
        elif company.job_board == "workable":
            sources[key] = workable_source(company)
        elif company.job_board == "hibob":
            sources[key] = hibob_source(company)
        elif company.job_board == "employmenthero":
            sources[key] = employmenthero_source(company)
        elif company.job_board == "smartrecruiters":
            sources[key] = smartrecruiters_source(company)
        elif company.job_board == "successfactors":
            sources[key] = successfactors_source(company)
        elif company.job_board == "avature":
            sources[key] = avature_source(company)
        elif company.job_board == "recruitee":
            sources[key] = recruitee_source(company)
        elif company.job_board == "oracle":
            sources[key] = oracle_source(company)
    return sources


COMPANY_SOURCES = _company_sources()
