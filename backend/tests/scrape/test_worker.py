import subprocess
import sys
import time
from pathlib import Path
from threading import Event

import pytest
from filelock import FileLock
from pytest import MonkeyPatch

from job_backend.scrape.worker import runner
from job_backend.scrape.worker.models import (
    ScheduledScrape,
    SourceGroup,
    WorkerSettings,
    WorkerState,
)
from job_backend.scrape.worker.scheduler import run_schedule
from job_backend.scrape.worker.state import load_state


def _settings() -> WorkerSettings:
    return WorkerSettings(
        tasks=[
            ScheduledScrape(group="github", interval_hours=3),
            ScheduledScrape(group="companies", interval_hours=6),
            ScheduledScrape(group="boards", interval_hours=6),
        ]
    )


def test_intervals_survive_restart(tmp_path: Path) -> None:
    path = tmp_path / "worker-state.json"
    settings = _settings()
    groups: list[SourceGroup] = []
    now = 1000.0

    def run(group: SourceGroup, *, resume_since: float | None = None) -> int:
        assert load_state(path).last_started[group] == now
        groups.append(group)
        return 0

    def cycle() -> int:
        return run_schedule(
            settings, load_state(path), path, Event(), run, once=True, clock=lambda: now
        )

    assert cycle() == 0
    assert groups == ["github", "companies", "boards"]
    groups.clear()
    now += 3 * 3600 - 1
    assert cycle() == 0 and groups == []
    now += 1
    assert cycle() == 0 and groups == ["github"]
    groups.clear()
    now += 3 * 3600
    assert cycle() == 0 and groups == ["github", "companies", "boards"]
    groups.clear()
    now += 30 * 86400
    assert cycle() == 0 and groups == ["github", "companies", "boards"]
    assert not path.with_suffix(".tmp").exists()


@pytest.mark.parametrize(
    "error", [OSError("Fictional child startup failure"), RuntimeError("Fictional runner failure")]
)
@pytest.mark.parametrize("exit_code", [1, 124])
def test_failed_group_isolated(
    tmp_path: Path, error: Exception, exit_code: int, caplog: pytest.LogCaptureFixture
) -> None:
    groups: list[SourceGroup] = []
    path = tmp_path / "worker-state.json"

    def run(group: SourceGroup, *, resume_since: float | None = None) -> int:
        groups.append(group)
        if group == "github":
            raise error
        return exit_code if group == "companies" else 0

    settings = _settings()
    assert (
        run_schedule(settings, WorkerState(), path, Event(), run, once=True, clock=lambda: 1000.0)
        == 1
    )
    assert groups == ["github", "companies", "boards"]
    assert "Could not run github importer; continuing the schedule" in caplog.text
    assert type(error).__name__ in caplog.text
    groups.clear()
    assert (
        run_schedule(
            settings, load_state(path), path, Event(), run, once=True, clock=lambda: 1001.0
        )
        == 0
    )
    assert groups == []


@pytest.mark.parametrize("cancel", [False, True])
def test_subprocess_stopped(tmp_path: Path, monkeypatch: MonkeyPatch, cancel: bool) -> None:
    settings = _settings().model_copy(
        update={"max_run_seconds": 1.0, "shutdown_grace_seconds": 1.0}
    )
    processes: list[subprocess.Popen[bytes]] = []
    original_stop = runner.stop_scrape_process

    def command(_group: SourceGroup, _database: Path) -> list[tuple[str, list[str]]]:
        return [("offline-source", [sys.executable, "-c", "import time; time.sleep(60)"])]

    def stop_child(process: subprocess.Popen[bytes], grace_seconds: float) -> None:
        assert process.poll() is None
        processes.append(process)
        original_stop(process, grace_seconds)

    stop = Event()
    if cancel:
        stop.set()
    monkeypatch.setattr(runner, "build_scrape_commands", command)
    monkeypatch.setattr(runner, "stop_scrape_process", stop_child)
    started = time.monotonic()
    try:
        assert runner.run_scrape_process("github", tmp_path / "postgres", settings, stop) == (
            130 if cancel else 124
        )
        assert len(processes) == 1
        assert processes[0].poll() is not None
        assert time.monotonic() - started < 10
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()


def _marker_child(markers: Path, name: str) -> list[str]:
    return [
        sys.executable,
        "-c",
        "import pathlib, sys, time\n"
        f"root = pathlib.Path({str(markers)!r})\n"
        f"(root / {name!r}).write_text(str(time.time()))\n"
        "deadline = time.time() + 5\n"
        "while time.time() < deadline:\n"
        "    if len(list(root.iterdir())) >= 2:\n"
        "        raise SystemExit(0)\n"
        "    time.sleep(0.05)\n"
        "raise SystemExit(3)\n",
    ]


def test_parallel_sources(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    markers = tmp_path / "markers"
    markers.mkdir()
    settings = WorkerSettings(
        tasks=[ScheduledScrape(group="companies", interval_hours=6, parallel_sources=2)]
    )

    def commands(_group: SourceGroup, _database: Path) -> list[tuple[str, list[str]]]:
        return [(name, _marker_child(markers, name)) for name in ("alpha", "beta", "gamma")]

    def lanes(_group: SourceGroup) -> dict[str, str]:
        return {"alpha": "greenhouse", "beta": "greenhouse", "gamma": "ashby"}

    monkeypatch.setattr(runner, "build_scrape_commands", commands)
    monkeypatch.setattr(runner, "source_lanes", lanes)
    started = time.monotonic()
    assert runner.run_scrape_process("companies", tmp_path / "postgres", settings, Event()) == 0
    assert time.monotonic() - started < 10
    order = sorted(markers.iterdir(), key=lambda marker: float(marker.read_text()))
    names = [marker.name for marker in order]
    assert set(names[:2]) == {"alpha", "gamma"}
    assert names[2] == "beta"


def test_supervisor_holds_lock(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    database = tmp_path / "postgres"
    child = [
        sys.executable,
        "-c",
        "import os, sys\n"
        "from filelock import FileLock, Timeout\n"
        "assert os.environ['JOB_SCRAPE_SUPERVISED'] == '1'\n"
        "try:\n"
        "    FileLock(sys.argv[1] + '.import.lock', timeout=0).acquire()\n"
        "except Timeout:\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(5)\n",
        str(database),
    ]

    def commands(_group: SourceGroup, _database: Path) -> list[tuple[str, list[str]]]:
        return [("offline-source", child)]

    monkeypatch.setattr(runner, "build_scrape_commands", commands)
    assert runner.run_scrape_process("github", database, _settings(), Event()) == 0
    with FileLock(str(database) + ".import.lock", timeout=0):
        assert runner.run_scrape_process("github", database, _settings(), Event()) == 2


def test_brief_failure_retried(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    attempts = tmp_path / "attempts"
    attempts.mkdir()

    def commands(_group: SourceGroup, _database: Path) -> list[tuple[str, list[str]]]:
        return [
            (
                name,
                [
                    sys.executable,
                    "-c",
                    "import pathlib, sys, time\n"
                    f"(pathlib.Path({str(attempts)!r}) / str(time.time())).write_text({name!r})",
                ],
            )
            for name in ("flaky", "steady")
        ]

    checks: list[float] = []

    def failures(_engine: object, since: float) -> set[str]:
        checks.append(since)
        return {"flaky"}

    monkeypatch.setattr(runner, "build_scrape_commands", commands)
    monkeypatch.setattr(runner, "transient_failures", failures)
    monkeypatch.setattr(runner, "RETRY_PAUSE_SECONDS", 0.0)
    assert runner.run_scrape_process("github", tmp_path / "postgres", _settings(), Event()) == 0
    names = sorted(path.read_text() for path in attempts.iterdir())
    assert names == ["flaky", "flaky", "steady"]
    assert len(checks) == 1
