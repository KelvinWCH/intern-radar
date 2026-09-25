import subprocess
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from filelock import Timeout
from pytest import MonkeyPatch

from job_backend import cli
from job_backend.scrape.worker.ownership import scrape_execution_lock

_OWNER_SCRIPT = """
import sys, time
from pathlib import Path
from job_backend.scrape.worker.ownership import scrape_execution_lock
with scrape_execution_lock(Path(sys.argv[1])):
    Path(sys.argv[2]).write_text('ready', encoding='utf-8')
    time.sleep(60)
"""


@contextmanager
def _owner(state: Path, ready: Path) -> Generator[subprocess.Popen[bytes]]:
    with subprocess.Popen([sys.executable, "-c", _OWNER_SCRIPT, str(state), str(ready)]) as process:
        try:
            deadline = time.monotonic() + 10
            while not ready.exists() and time.monotonic() < deadline:
                assert process.poll() is None, "Lock-owning child exited before it was ready"
                time.sleep(0.01)
            assert ready.exists(), "Lock-owning child did not become ready"
            yield process
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)


def test_import_lock(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    state = tmp_path / "postgres"
    open_database = MagicMock(side_effect=AssertionError("A busy CLI must not open PostgreSQL"))
    monkeypatch.setattr(cli, "make_engine", open_database)
    with _owner(state, tmp_path / "ready") as process:
        with pytest.raises(Timeout), scrape_execution_lock(tmp_path / "." / "postgres"):
            pass
        assert cli.main(["--state-path", str(state)]) == 2
        open_database.assert_not_called()
        process.kill()
        process.wait(timeout=10)
        lock = scrape_execution_lock(state)
        with lock.acquire(timeout=2):
            assert lock.is_locked
