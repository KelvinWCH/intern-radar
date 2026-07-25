from filelock import Timeout

from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.scrape.control.models import ScrapeActivity, ScrapeEventResponse
from job_backend.scrape.models import ScrapeEvent, ScrapeRun
from job_backend.scrape.pipeline.models import ScrapeRunResponse
from job_backend.scrape.worker.control import read_scheduled_scrape
from job_backend.scrape.worker.ownership import process_lock


def scrape_activity(engine: Database) -> ScrapeActivity:
    scheduled = read_scheduled_scrape(engine.local_path)
    busy = scheduled is not None
    for lock in (
        process_lock(engine.local_path, "import"),
        process_lock(engine.local_path, "ui-scrape"),
    ):
        try:
            with lock:
                pass
        except Timeout:
            busy = True
            break
    if not busy:
        return ScrapeActivity(busy=False)
    with Session(engine, read_only=True) as session:
        runs = session.find(ScrapeRun, equal={"status": "running"}, order_by=("started_at", "id"))
        events: list[ScrapeEvent] = (
            session.filtered_recent(
                ScrapeEvent, "created_at", limit=80, one_of=("run_id", [run.id for run in runs])
            )
            if runs
            else []
        )
        return ScrapeActivity(
            busy=True,
            scheduled=scheduled,
            runs=[ScrapeRunResponse.model_validate(run) for run in runs],
            events=[ScrapeEventResponse.model_validate(event) for event in reversed(events)],
        )
