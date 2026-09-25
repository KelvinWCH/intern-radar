import time
from contextlib import nullcontext
from pathlib import Path
from typing import Literal

from filelock import Timeout

from job_backend.common.logger import get_logger
from job_backend.persistence.database import Database, make_engine
from job_backend.persistence.session import Session
from job_backend.scrape.models import ScrapeRun
from job_backend.scrape.pipeline.telemetry.events import EventRecorder
from job_backend.scrape.worker.ownership import scrape_execution_lock

logger = get_logger(__name__)


def recover_interrupted_scrape_runs(engine: Database) -> None:
    with Session(engine) as session, session.begin():
        for row in session.find(ScrapeRun, equal={"status": "running"}):
            row.status = "failed"
            row.finished_at = int(time.time())
            row.phase = "interrupted"
            row.error = "The previous importer stopped before this source finished. Retry the run."


def finish_stopped_source(
    database: Path,
    source: str,
    started_at: float,
    reason: str,
    *,
    phase: Literal["timeout", "interrupted"],
    engine: Database | None = None,
) -> None:
    owned = engine is None
    try:
        with scrape_execution_lock(database) if owned else nullcontext():
            if engine is None:
                engine = make_engine(database)
            with Session(engine) as session, session.begin():
                for row in session.find(
                    ScrapeRun, equal={"source": source, "trigger": "cron", "status": "running"}
                ):
                    if row.started_at < started_at:
                        continue
                    row.status = "failed"
                    row.phase = phase
                    row.finished_at = time.time()
                    row.error = reason
                    EventRecorder(engine, row.id, row.task_id)(
                        reason, "warning" if phase == "timeout" else "error"
                    )
    except Timeout:
        logger.warning("Stopped %s; history recovery deferred to the active importer", source)
    except Exception:
        logger.exception("Could not finalize stopped source %s; recovery will retry", source)
    finally:
        if owned and engine is not None:
            engine.dispose()
