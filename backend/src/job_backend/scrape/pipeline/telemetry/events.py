import time

from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.scrape.models import ScrapeEvent
from job_backend.scrape.pipeline.telemetry.models import ScrapeEventLevel


class EventRecorder:
    def __init__(self, engine: Database, run_id: str, task_id: str | None) -> None:
        self.engine = engine
        self.run_id = run_id
        self.task_id = task_id

    def __call__(self, message: str, level: ScrapeEventLevel = "info") -> None:
        try:
            with Session(self.engine) as session, session.begin():
                session.add(
                    ScrapeEvent(
                        run_id=self.run_id,
                        task_id=self.task_id,
                        created_at=time.time(),
                        level=level,
                        message=message[:500],
                    )
                )
        except Exception:
            return
