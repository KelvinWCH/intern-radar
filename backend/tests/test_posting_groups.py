from job_backend.jobs.browsing import Sort, browse_jobs, job_overview
from job_backend.jobs.deduplication import deduplication_key, job_url_hash
from job_backend.jobs.models import Job, JobPage, JobUserRecord
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from tests.test_postgres import postgres as postgres

WORKDAY = (
    "https://trimble.wd1.myworkdayjobs.com/en-US/TrimbleCareers/job/Canada---Richmond-Hill-"
    "Ontario-Applanix/Software-Engineering-Intern_R57963?utm_source=Simplify&ref=Simplify",
    "https://trimble.wd1.myworkdayjobs.com/en-US/trimblecareers/job/Canada---Richmond-Hill-"
    "Ontario-Applanix/Software-Engineering-Intern_R57963",
    "https://trimble.wd1.myworkdayjobs.com/TrimbleCareers/job/Canada---Richmond-Hill-Ontario-"
    "Applanix/Software-Engineering-Intern_R57963",
)


def _job(identity: str, url: str | None, company: str, **fields: object) -> Job:
    job = Job(
        id=identity,
        source="board",
        title="Software Engineering Intern",
        company=company,
        application_url=url,
        is_canada_internship=True,
        is_toronto_area=True,
        first_seen_at=1,
        job_hash="a" * 64,
        content_hash="b" * 64,
    )
    for name, value in fields.items():
        setattr(job, name, value)
    job.job_url_hash = job_url_hash(url) if url else None
    job.deduplication_key = deduplication_key(job)
    return job


def _save(engine: Database, jobs: list[Job], users: tuple[JobUserRecord, ...] = ()) -> None:
    with Session(engine) as session, session.begin():
        for job in jobs:
            session.add(job)
        for user in users:
            session.add(user)


def _browse(
    session: Session,
    *,
    sort: Sort | None = "match",
    scope: str = "eligible",
    tracked: bool = False,
    flagged: bool | None = None,
    limit: int = 10,
    offset: int = 0,
) -> JobPage:
    return browse_jobs(
        session,
        limit=limit,
        offset=offset,
        active=None,
        toronto_area=None,
        first_seen_from=None,
        first_seen_before=None,
        posted_from=None,
        posted_before=None,
        posted_timezone="UTC",
        q="",
        company="",
        location="",
        source=None,
        application_status=None,
        tracked=tracked,
        deleted=False,
        flagged=flagged,
        scope=scope,
        sort=sort,
    )


def test_board_copies_collapse(engine: Database) -> None:
    spellings = ("Trimble", "211 Applanix Corporation", "TRIMBLE INC.")
    copies = [
        _job(f"copy-{index}", url, name, source=f"board-{index}", first_seen_at=100 + index)
        for index, (url, name) in enumerate(zip(WORKDAY, spellings, strict=True))
    ]
    alone = _job("alone", "https://careers.example.com/jobs/1", "Example", first_seen_at=50)
    unlinked = _job("unlinked", None, "Nowhere", source="paste", first_seen_at=10)
    _save(engine, [*copies, alone, unlinked], (JobUserRecord(job_id="copy-1", status="applied"),))
    with Session(engine, read_only=True) as session:
        page = _browse(session, sort="recent")
        assert page.total == 3
        assert [(item.id, item.copies) for item in page.items] == [
            ("copy-1", 3),
            ("alone", 1),
            ("unlinked", 1),
        ]
        assert page.items[0].user.status == "applied"
        assert page.items[0].model_dump().get("deduplication_key") is None
        tracked = _browse(session, tracked=True)
        assert tracked.total == 1 and [item.id for item in tracked.items] == ["copy-1"]
        second = _browse(session, sort="recent", limit=2, offset=2)
        assert second.total == 3 and [item.id for item in second.items] == ["unlinked"]
        overview = job_overview(session, deleted=False, eligible=True)
        assert overview.statuses == {"new": 3, "applied": 1} and overview.total == 4
        assert overview.sources == ["board", "board-0", "board-1", "board-2", "paste"]
