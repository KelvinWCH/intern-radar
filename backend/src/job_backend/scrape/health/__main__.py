import time

from job_backend.persistence.database import default_database_path, make_engine
from job_backend.persistence.session import Session
from job_backend.scrape.health.regressions import scrape_health
from job_backend.scrape.worker.settings import load_settings
from job_backend.scrape.worker.sources import scheduled_sources


def main() -> int:
    engine = make_engine(default_database_path())
    try:
        with Session(engine, read_only=True) as session:
            health = scrape_health(session, scheduled_sources(load_settings()), time.time())
    finally:
        engine.dispose()
    print(health.model_dump_json(indent=2))
    return 1 if health.regressions else 0


if __name__ == "__main__":
    raise SystemExit(main())
