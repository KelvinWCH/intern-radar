from job_backend.jobs.constants import ENGINEERING_TITLE


def engineering_title_priority(title: str) -> int:
    return 0 if ENGINEERING_TITLE.search(title) else 1
