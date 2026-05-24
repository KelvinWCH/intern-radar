from job_backend.scrape.worker.models import SourceGroup

GROUP_ARGUMENTS: dict[SourceGroup, str] = {
    "github": "--repo",
    "boards": "--company",
    "companies": "--company",
}

API_BOARDS = frozenset(
    {
        "greenhouse",
        "lever",
        "ashby",
        "workable",
        "smartrecruiters",
        "hibob",
        "recruitee",
        "employmenthero",
    }
)


STAGE_LABELS = {
    "discovering": "Finding postings",
    "checking cache": "Checking for changes",
    "reading and extracting": "Reading postings",
    "saving": "Saving jobs",
}

OUTCOME_LABELS = {
    0: ("Scrape complete", 0xA6DA95),
    124: ("Scrape reached its time limit", 0xEED49F),
    130: ("Scrape stopped", 0xEED49F),
    3: ("Scrape waiting for the internet", 0xEED49F),
}
