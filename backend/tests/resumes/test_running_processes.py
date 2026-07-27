import time
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from job_backend.jobs.models import JobDocument, JobUserRecord
from job_backend.jobs.user_routes import create_router
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session


def test_abandoned_work_expires(engine: Database) -> None:
    document_id = str(uuid4())
    with Session(engine) as session:
        session.add(
            JobDocument(
                id=document_id,
                job_id="interrupted-job",
                company="Example",
                title="Intern",
                status="running",
                created_at=int(time.time()) - 7201,
            )
        )
        session.add(JobUserRecord(job_id="interrupted-job", active_document_id=document_id))
        session.commit()
    app = FastAPI()
    app.include_router(create_router(engine))
    with TestClient(app) as client:
        assert client.get("/documents/active").json() == []
    with Session(engine) as session:
        document = session.get(JobDocument, document_id)
        assert document is not None
        assert document.status == "failed"
        user = session.find(JobUserRecord, equal={"job_id": "interrupted-job"}).one()
        assert user.active_document_id is None
