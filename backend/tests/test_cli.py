from pathlib import Path

import httpx2
import pytest
from filelock import FileLock
from pytest import CaptureFixture, MonkeyPatch

from job_backend import cli
from job_backend.persistence.database import Database
from job_backend.scrape.companies.company_sources import COMPANY_SOURCES
from job_backend.scrape.github.github import DEFAULT_REPOSITORY, REPOSITORIES
from job_backend.scrape.models import ScrapeTrigger
from job_backend.scrape.pipeline.models import (
    JobSource,
    ScrapeRunResponse,
)


@pytest.mark.parametrize("trigger", ["manual", "cron"])
@pytest.mark.parametrize("use_ai", [False, True])
@pytest.mark.parametrize("selection", ["default", "chosen", "company"])
def test_cli_selects_repositories(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    selection: str,
    capsys: CaptureFixture[str],
    trigger: ScrapeTrigger,
    use_ai: bool,
) -> None:
    selected: list[str] = []
    expected_trigger = trigger
    expected_use_ai = use_ai

    def fake_import(
        _engine: Database,
        source: JobSource,
        *,
        task_id: str | None = None,
        trigger: ScrapeTrigger | None = None,
        use_ai: bool = False,
    ) -> ScrapeRunResponse:
        assert trigger == expected_trigger
        assert use_ai == expected_use_ai
        selected.append(source.name)
        return ScrapeRunResponse(
            id=f"run-{len(selected)}",
            source=source.name,
            status="completed",
            started_at=1,
            finished_at=2,
            fetched=1,
            matched=1,
            created=1,
            updated=0,
            unchanged=0,
            error=None,
        )

    arguments = ["job-import", "--state-path", str(tmp_path / "postgres"), "--trigger", trigger]
    if use_ai:
        arguments.append("--use-ai")
    if selection == "chosen":
        arguments += ["--repo", "speedyapply-swe-2027", "--repo", "speedyapply-swe-2027"]
    elif selection == "company":
        arguments += ["--company", "waabi", "--company", "waabi"]
    monkeypatch.setattr("sys.argv", arguments)
    monkeypatch.setattr(cli, "scrape_source", fake_import)
    assert cli.main() == 0
    expected = {
        "default": [DEFAULT_REPOSITORY],
        "chosen": ["speedyapply-swe-2027"],
        "company": [COMPANY_SOURCES["waabi"].name],
    }[selection]
    assert selected == expected
    assert len(capsys.readouterr().out.splitlines()) == len(expected)


@pytest.mark.parametrize(
    ("error_type", "exit_code"), [(ValueError, 1), (TimeoutError, 0), (httpx2.ReadTimeout, 0)]
)
def test_cli_continues_after_failure(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
    error_type: type[Exception],
    exit_code: int,
) -> None:
    selected: list[str] = []

    def fake_import(
        _engine: Database,
        source: JobSource,
        *,
        task_id: str | None = None,
        trigger: ScrapeTrigger | None = None,
        use_ai: bool = False,
    ) -> ScrapeRunResponse:
        selected.append(source.name)
        if source.name == DEFAULT_REPOSITORY:
            raise error_type("Fictional broken file")
        return ScrapeRunResponse(
            id="run-1",
            source=source.name,
            status="completed",
            started_at=1,
            finished_at=2,
            fetched=0,
            matched=0,
            created=0,
            updated=0,
            unchanged=0,
            error=None,
        )

    monkeypatch.setattr(
        "sys.argv", ["job-import", "--state-path", str(tmp_path / "postgres"), "--all-repos"]
    )
    monkeypatch.setattr(cli, "scrape_source", fake_import)
    assert cli.main() == exit_code
    assert selected == list(REPOSITORIES)
    error = capsys.readouterr().err
    if exit_code:
        assert "Fictional broken file" in error and " ERROR " in error
    else:
        assert f"Skipped {DEFAULT_REPOSITORY} until the next run" in error
        assert " ERROR " not in error


def test_cli_locked(tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]) -> None:
    database = tmp_path / "postgres"

    def unexpected_import(
        _engine: Database,
        _source: JobSource,
        *,
        task_id: str | None = None,
        trigger: ScrapeTrigger | None = None,
        use_ai: bool = False,
    ) -> ScrapeRunResponse:
        pytest.fail("A locked importer must not start a source")

    monkeypatch.setattr(cli, "scrape_source", unexpected_import)
    with FileLock(str(database) + ".import.lock", timeout=0):
        assert cli.main(["--state-path", str(database)]) == 2
    assert not database.exists()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "already running" in captured.err


def test_cli_unknown_repo(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    database = tmp_path / "postgres"
    monkeypatch.setattr(
        "sys.argv", ["job-import", "--state-path", str(database), "--repo", "missing"]
    )
    with pytest.raises(SystemExit) as caught:
        cli.main()
    assert caught.value.code == 2 and not database.exists()
