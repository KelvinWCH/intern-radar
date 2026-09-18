from pathlib import Path
from typing import Literal

from filelock import FileLock


def process_lock(
    state_path: Path, name: Literal["import", "ui-scrape", "worker", "scheduled-scrape"]
) -> FileLock:
    path = state_path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return FileLock(str(path) + f".{name}.lock", timeout=0, thread_local=False)


def scrape_execution_lock(state_path: Path) -> FileLock:
    return process_lock(state_path, "import")
