import os
from pathlib import Path

from job_backend.common.environment import load_environment
from job_backend.scrape.worker.models import WorkerSettings


def load_settings() -> WorkerSettings:
    load_environment()
    configured = os.environ.get("JOB_WORKER_CONFIG_FILE")
    path = Path(configured) if configured else Path(__file__).with_name("schedules.json")
    return WorkerSettings.model_validate_json(path.read_bytes(), strict=True)
