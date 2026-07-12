from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from job_backend.persistence.database import Database
from job_backend.scrape.control.activity import scrape_activity
from job_backend.scrape.control.routes import create_router
from job_backend.scrape.control.service import ScrapeController
from job_backend.scrape.worker.control import (
    read_scheduled_scrape,
    scheduled_scrape_control,
)
from job_backend.scrape.worker.ownership import scrape_execution_lock


def test_cancel_route(engine: Database) -> None:
    app = FastAPI()
    app.include_router(create_router(engine, ScrapeController(engine)))
    with TestClient(app) as client:
        assert client.post("/scrapes/scheduled/not-a-uuid/cancel").status_code == 422
        with scheduled_scrape_control(engine.local_path, "companies") as control:
            activity = client.get("/scrapes/activity").json()
            assert activity["busy"]
            assert activity["scheduled"]["id"] == control.id
            assert not activity["scheduled"]["cancel_requested"]
            assert client.post(f"/scrapes/scheduled/{uuid4()}/cancel").status_code == 409
            for _ in range(2):
                response = client.post(f"/scrapes/scheduled/{control.id}/cancel")
                assert response.status_code == 200
                assert response.json()["scheduled"]["cancel_requested"]
        assert client.get("/scrapes/activity").json()["scheduled"] is None
        with scheduled_scrape_control(engine.local_path, "github") as next_control:
            assert client.post(f"/scrapes/scheduled/{control.id}/cancel").status_code == 409
            assert not next_control.cancel_requested
            current = read_scheduled_scrape(engine.local_path)
            assert current is not None and not current.cancel_requested
        with scrape_execution_lock(engine.local_path):
            assert client.post(f"/scrapes/scheduled/{control.id}/cancel").status_code == 409
            assert scrape_activity(engine).busy
