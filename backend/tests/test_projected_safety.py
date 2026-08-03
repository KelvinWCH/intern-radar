import pytest

from job_backend.jobs.models import Job
from job_backend.persistence.database import Database
from job_backend.persistence.models import ReadQuery
from job_backend.persistence.session import Session


def test_snapshots_dont_replace_source(engine: Database) -> None:
    source = Job(
        id="full", raw_payload={"huge": "x" * 100_000}, raw_description="Complete original"
    )
    with Session(engine) as session, session.begin():
        session.add(source)
    with Session(engine) as session:
        projected = session.select(ReadQuery("jobs", fields=("id", "title")), limit=1).items[0]
        projected["title"] = "Detached change"
        assert not session.expected and not session.records
        session.commit()
        full = session.get(Job, "full", hydrate=False)
        assert full is not None and full.raw_description == source.raw_description
        assert full.raw_payload == source.raw_payload
        assert full.title != projected["title"]
        full.title = "A real edit"
        session.commit()
    with Session(engine, read_only=True) as session:
        assert session.select(ReadQuery("jobs"), limit=1).items[0]["title"] == "A real edit"
        with pytest.raises(RuntimeError, match="Read-only"):
            session.commit()
