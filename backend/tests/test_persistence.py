import pytest

from job_backend.jobs.models import Job, JobUserRecord
from job_backend.persistence.database import Database
from job_backend.persistence.errors import ConflictError
from job_backend.persistence.identity import document_id
from job_backend.persistence.session import Session


def test_keys_dont_collide() -> None:
    assert document_id((42,)) == "42"
    identities = [("a/b",), ("a", "b"), ("a:b",), ("a:b", "c"), ("a", "b:c")]
    encoded = {document_id(identity) for identity in identities}
    assert len(encoded) == len(identities)
    assert all("/" not in identity for identity in encoded)


def test_stale_session(engine: Database) -> None:
    with Session(engine) as setup, setup.begin():
        setup.add(JobUserRecord(job_id="job-one"))
    with Session(engine) as older, Session(engine) as newer:
        old = older.get(JobUserRecord, "job-one")
        new = newer.get(JobUserRecord, "job-one")
        assert old is not None and new is not None
        new.notes = "Keep the newer edit"
        new.version += 1
        newer.commit()
        old.notes = "Stale edit"
        older.add(JobUserRecord(job_id="job-two"))
        with pytest.raises(ConflictError):
            older.commit()
    with Session(engine) as check:
        saved = check.get(JobUserRecord, "job-one")
        assert saved is not None and saved.notes == "Keep the newer edit"
        assert check.get(JobUserRecord, "job-two") is None


def test_duplicate_identities(engine: Database) -> None:
    with Session(engine) as session:
        session.add(Job(source="feed", external_id="same", job_hash="same"))
        with pytest.raises(ConflictError):
            session.add(Job(source="feed", external_id="same", job_hash="same"))
    assert engine.gateway.find("jobs", {}) == []
