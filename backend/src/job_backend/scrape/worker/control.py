import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from filelock import FileLock, Timeout
from pydantic import ValidationError

from job_backend.scrape.worker.models import ScheduledScrapeControl, SourceGroup
from job_backend.scrape.worker.ownership import process_lock


def _control_path(database: Path) -> Path:
    return Path(str(database.expanduser().resolve()) + ".scheduled-scrape.json")


def _control_lock(database: Path) -> FileLock:
    return FileLock(str(_control_path(database)) + ".lock", timeout=5)


def _read_control(database: Path) -> ScheduledScrapeControl | None:
    try:
        with process_lock(database, "scheduled-scrape"):
            return None
    except Timeout:
        pass
    try:
        return ScheduledScrapeControl.model_validate_json(_control_path(database).read_bytes())
    except (FileNotFoundError, ValidationError):
        return None


@contextmanager
def scheduled_scrape_control(
    database: Path, group: SourceGroup
) -> Generator[ScheduledScrapeControl]:
    control = ScheduledScrapeControl(id=str(uuid4()), group=group, started_at=time.time())
    with process_lock(database, "scheduled-scrape"):
        try:
            with _control_lock(database):
                _control_path(database).write_text(control.model_dump_json(), encoding="utf-8")
            yield control
        finally:
            with _control_lock(database):
                _control_path(database).unlink(missing_ok=True)


def read_scheduled_scrape(database: Path) -> ScheduledScrapeControl | None:
    with _control_lock(database):
        return _read_control(database)


def cancel_scheduled_scrape(database: Path, identifier: str) -> ScheduledScrapeControl:
    with _control_lock(database):
        control = _read_control(database)
        if control is None or control.id != identifier:
            raise ValueError("This scheduled scrape has finished. Refresh the running processes.")
        control.cancel_requested = True
        _control_path(database).write_text(control.model_dump_json(), encoding="utf-8")
        return control
