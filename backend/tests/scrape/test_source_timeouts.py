import os
import subprocess
import sys
import time
from pathlib import Path
from threading import Event

import pytest
from pytest import MonkeyPatch

from job_backend.scrape.companies.company_sources import COMPANY_SOURCES
from job_backend.scrape.worker import runner
from job_backend.scrape.worker.models import ScheduledScrape, SourceGroup, WorkerSettings


@pytest.mark.parametrize("group", ["github", "boards", "companies"])
def test_timeout_runs_next(tmp_path: Path, monkeypatch: MonkeyPatch, group: SourceGroup) -> None:
    marker = tmp_path / "next-source"
    settings = WorkerSettings(
        tasks=[ScheduledScrape(group=group, interval_hours=3)],
        max_source_seconds=1,
        max_run_seconds=20,
        shutdown_grace_seconds=1,
    )

    def commands(_group: SourceGroup, _database: Path) -> list[tuple[str, list[str]]]:
        return [
            ("stuck-source", [sys.executable, "-c", "import time; time.sleep(60)"]),
            (
                "next-source",
                [
                    sys.executable,
                    "-c",
                    "import pathlib, sys; pathlib.Path(sys.argv[1]).write_text('completed')",
                    str(marker),
                ],
            ),
        ]

    stopped: list[subprocess.Popen[bytes]] = []
    stop_process = runner.stop_scrape_process

    def stop_child(process: subprocess.Popen[bytes], grace_seconds: float) -> None:
        stopped.append(process)
        stop_process(process, grace_seconds)

    monkeypatch.setattr(runner, "build_scrape_commands", commands)
    monkeypatch.setattr(runner, "stop_scrape_process", stop_child)
    started = time.monotonic()
    assert runner.run_scrape_process(group, tmp_path / "postgres", settings, Event()) == 0
    assert marker.read_text() == "completed"
    assert len(stopped) == 2 and all(process.poll() is not None for process in stopped)
    assert time.monotonic() - started < 10


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups are used by the deployed worker")
def test_timeout_kills_children(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    marker = tmp_path / "orphaned-browser"
    browser_script = (
        "import pathlib, signal, sys, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "time.sleep(3); pathlib.Path(sys.argv[1]).touch()"
    )
    importer_script = (
        "import subprocess, sys, time; "
        "subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]]); time.sleep(60)"
    )

    def commands(_group: SourceGroup, _database: Path) -> list[tuple[str, list[str]]]:
        return [
            (
                "stuck-source",
                [sys.executable, "-c", importer_script, browser_script, str(marker)],
            )
        ]

    monkeypatch.setattr(runner, "build_scrape_commands", commands)
    settings = WorkerSettings(
        tasks=[ScheduledScrape(group="companies", interval_hours=12)],
        max_source_seconds=1,
        shutdown_grace_seconds=1,
    )
    assert runner.run_scrape_process("companies", tmp_path / "postgres", settings, Event()) == 0
    time.sleep(3)
    assert not marker.exists()


def test_boards_and_companies(tmp_path: Path) -> None:
    boards = {name for name, _ in runner.build_scrape_commands("boards", tmp_path / "db")}
    companies = {name for name, _ in runner.build_scrape_commands("companies", tmp_path / "db")}
    assert not boards & companies
    assert boards | companies == {source.name for source in COMPANY_SOURCES.values()}
    assert any(name.startswith("greenhouse-") for name in boards)
    assert any(name.startswith("workday-") for name in companies)
