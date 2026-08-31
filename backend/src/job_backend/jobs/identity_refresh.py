import time

from job_backend.jobs.deduplication import deduplication_key, job_url_hash
from job_backend.jobs.models import IdentityState, Job
from job_backend.persistence.database import Database
from job_backend.persistence.models import ReadQuery
from job_backend.persistence.session import Session

IDENTITY_VERSION = 2
_PAGE = 1000
_BATCH = 200
_FIELDS = (
    "id",
    "application_url",
    "source_job_id",
    "company",
    "deduplication_key",
    "job_url_hash",
)


def expected_keys(job: Job) -> tuple[str | None, str | None]:
    url_hash = job_url_hash(job.application_url) if job.application_url else None
    return url_hash, deduplication_key(job)


def _stale_ids(session: Session) -> list[str]:
    query = ReadQuery("jobs", fields=_FIELDS)
    stale: list[str] = []
    offset = 0
    while True:
        rows = session.select(query, limit=_PAGE, offset=offset, count=False).items
        for row in rows:
            identity = row.get("id")
            if not isinstance(identity, str):
                continue
            url, source_job_id, company = (
                row.get("application_url"),
                row.get("source_job_id"),
                row.get("company"),
            )
            probe = Job(
                id=identity,
                company=company if isinstance(company, str) else "",
                application_url=url if isinstance(url, str) else None,
                source_job_id=source_job_id if isinstance(source_job_id, str) else None,
            )
            if (row.get("job_url_hash"), row.get("deduplication_key")) != expected_keys(probe):
                stale.append(identity)
        if len(rows) < _PAGE:
            return stale
        offset += _PAGE


def refresh_identities(engine: Database) -> int:
    with Session(engine, read_only=True) as session:
        state = session.get(IdentityState, "current", hydrate=False)
        if state is not None and state.version >= IDENTITY_VERSION:
            return 0
        stale = _stale_ids(session)
    changed = 0
    for start in range(0, len(stale), _BATCH):
        batch = stale[start : start + _BATCH]
        with Session(engine) as session, session.begin():
            session.prefetch(Job, set(batch))
            for identity in batch:
                job = session.get(Job, identity, hydrate=False)
                if job is None:
                    continue
                url_hash, key = expected_keys(job)
                if (job.job_url_hash, job.deduplication_key) != (url_hash, key):
                    job.job_url_hash = url_hash
                    job.deduplication_key = key
                    changed += 1
    with Session(engine) as session, session.begin():
        state = session.get(IdentityState, "current", hydrate=False)
        if state is None:
            state = IdentityState()
            session.add(state)
        state.version = IDENTITY_VERSION
        state.refreshed_at = int(time.time())
        state.changed = changed
    return changed
