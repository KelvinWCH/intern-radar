from pathlib import Path

from filelock import FileLock
from pytest import MonkeyPatch

from job_backend.cli import main
from job_backend.persistence.database import Database, migrate


def test_no_local_data(engine: Database) -> None:
    migrate(engine)
    migrate(engine)
    assert not engine.local_path.exists()


def test_cli_refuses_overlapping_imports(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    database = tmp_path / "postgres"
    monkeypatch.setattr("sys.argv", ["job-import", "--state-path", str(database)])
    with FileLock(str(database) + ".import.lock", timeout=0):
        assert main() == 2
    assert not database.exists()
