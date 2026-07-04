from job_backend.jobs.identity import job_document_id
from job_backend.jobs.models import Job
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session


def test_job_keys_stable(engine: Database) -> None:
    assert job_document_id("feed", "42") == job_document_id("feed", "42")
    assert job_document_id("feed", "42") != job_document_id("other", "42")
    assert job_document_id("user", "text-a", "https://example.com/job?utm_source=a") == (
        job_document_id("user", "text-b", "https://example.com/job")
    )
    assert job_document_id("user", "text-a") != job_document_id("user", "text-b")
    with Session(engine) as session, session.begin():
        job = Job(source="user", external_id="text-a", application_url="https://example.com/a")
        session.add(job)
    identity = job.id
    with Session(engine) as session, session.begin():
        saved = session.get(Job, identity)
        assert saved is not None
        saved.application_url = "https://example.com/b"
        saved.assign_identity()
        assert saved.id == identity
