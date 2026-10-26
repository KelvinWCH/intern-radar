import argparse
import json
import logging
import os
import time
from contextlib import ExitStack
from pathlib import Path

from filelock import Timeout

from job_backend.common.logger import configure_logging, get_logger, shutdown_logging
from job_backend.common.models import LoggingSettings
from job_backend.persistence.database import Database, default_database_path, make_engine, migrate
from job_backend.scrape.companies.companies import COMPANIES
from job_backend.scrape.companies.company_sources import COMPANY_SOURCES
from job_backend.scrape.daily_notifications import publish_daily_jobs
from job_backend.scrape.github.github import DEFAULT_REPOSITORY, REPOSITORIES
from job_backend.scrape.models import ScrapeArguments, ScrapeTrigger
from job_backend.scrape.pipeline.models import JobSource
from job_backend.scrape.pipeline.pipeline import scrape_source
from job_backend.scrape.pipeline.telemetry.performance import failure_reason
from job_backend.scrape.utils.browser_policy import unattended_browser_mode
from job_backend.scrape.utils.pacing import import_request_mode
from job_backend.scrape.utils.source_skips import skip_reason, source_unavailable
from job_backend.scrape.worker.live_status import LiveStatus
from job_backend.scrape.worker.ownership import scrape_execution_lock
from job_backend.scrape.worker.recovery import recover_interrupted_scrape_runs
from job_backend.scrape.worker.runner import SUPERVISED_ENV

logger = get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import Canadian internships from GitHub lists and company job boards"
    )
    parser.add_argument(
        "--state-path",
        "--database",
        dest="database",
        type=Path,
        default=default_database_path(),
        help="Local process-lock path; PostgreSQL database is selected by environment/credentials",
    )
    parser.add_argument(
        "--trigger",
        choices=("manual", "cron", "cli"),
        default="cli",
        help="Record what launched this import: manual UI, cron/scheduled worker, or CLI.",
    )
    parser.add_argument(
        "--unattended",
        action="store_true",
        help="Run without a desktop; browsers always stay headless.",
    )
    selection = parser.add_mutually_exclusive_group()
    parser.add_argument(
        "--use-ai",
        action="store_true",
        help="Explicitly enable paid AI extraction for this run; default uses local heuristics.",
    )
    selection.add_argument(
        "--repo",
        dest="repositories",
        action="append",
        choices=tuple(REPOSITORIES),
        help="Repository to import; repeat for multiple lists. Defaults to Simplify internships.",
    )
    selection.add_argument(
        "--all-repos",
        dest="all_repositories",
        action="store_true",
        help="Import every configured internship repository; keep Canadian internships only.",
    )
    companies = parser.add_mutually_exclusive_group()
    companies.add_argument(
        "--company",
        dest="companies",
        action="append",
        choices=tuple(COMPANIES),
        help="Company key from --list-companies; repeat to select multiple employers.",
    )
    companies.add_argument(
        "--all-companies",
        action="store_true",
        help="Import every supported company board; other careers sites are excluded.",
    )
    parser.add_argument(
        "--list-companies",
        action="store_true",
        help="Show the employer watchlist and supported boards without network or AI calls.",
    )
    arguments = ScrapeArguments()
    parser.parse_args(argv, namespace=arguments)
    if arguments.list_companies:
        print(
            json.dumps(
                [
                    {**company.model_dump(mode="json"), "can_import": company.supports_scraping}
                    for company in COMPANIES.values()
                ],
                indent=2,
            )
        )
        return 0
    for key in arguments.companies or []:
        if key not in COMPANY_SOURCES:
            parser.error(f"{COMPANIES[key].name} needs a dedicated careers-page discovery adapter")
    repositories = (
        list(REPOSITORIES)
        if arguments.all_repositories
        else arguments.repositories
        or ([] if (arguments.companies or arguments.all_companies) else [DEFAULT_REPOSITORY])
    )
    company_keys = list(COMPANY_SOURCES) if arguments.all_companies else arguments.companies or []
    selected_sources = list(
        {
            source.name: source
            for source in (
                *[REPOSITORIES[name] for name in repositories],
                *[COMPANY_SOURCES[key] for key in company_keys],
            )
        }.values()
    )
    database_path = Path(arguments.database).expanduser().resolve()
    with (
        unattended_browser_mode(arguments.unattended or arguments.trigger == "cron"),
        import_request_mode(scheduled=arguments.trigger == "cron"),
    ):
        return _run_scrape_sources(
            selected_sources, database_path, arguments.trigger, use_ai=arguments.use_ai
        )


def _run_scrape_sources(
    selected_sources: list[JobSource],
    database_path: Path,
    trigger: ScrapeTrigger,
    *,
    use_ai: bool = False,
) -> int:
    has_failures = False
    failed_sources = 0
    skipped_sources = 0
    job_totals = {"fetched": 0, "matched": 0, "created": 0, "updated": 0, "unchanged": 0}
    started_at_monotonic = time.monotonic()
    started_at = time.time()
    engine: Database | None = None
    live_status: LiveStatus | None = None
    exit_code = 1
    try:
        settings = LoggingSettings.from_environment()
    except ValueError as error:
        configure_logging(settings=LoggingSettings())
        logger.error("Invalid logging configuration: %s", error)
        shutdown_logging()
        return 1
    configure_logging(settings=settings)
    supervised = trigger == "cron" and os.environ.get(SUPERVISED_ENV) == "1"
    ownership = ExitStack()
    try:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        if not supervised:
            ownership.enter_context(scrape_execution_lock(database_path))
        if (
            settings.discord_scrape_webhook_url is not None
            and os.environ.get("JOB_DISCORD_LIVE_STATUS") != "1"
        ):
            live_status = LiveStatus(
                settings.discord_scrape_webhook_url,
                database_path,
                "import batch",
                trigger=trigger,
                sources={source.name for source in selected_sources},
            )
            live_status.start(background=True)
        engine = make_engine(database_path)
        migrate(engine)
        if not supervised:
            recover_interrupted_scrape_runs(engine)
        configure_logging(engine=engine, settings=settings)
        for source in selected_sources:
            try:
                logger.info(
                    "Import started for %s",
                    source.name,
                    extra={"context": {"source": source.name}},
                )
                scrape_result = scrape_source(
                    engine,
                    source,
                    task_id=os.environ.get("JOB_SCRAPE_TASK_ID"),
                    trigger=trigger,
                    use_ai=use_ai,
                )
                print(scrape_result.model_dump_json())
                job_totals["fetched"] += scrape_result.fetched
                job_totals["matched"] += scrape_result.matched
                job_totals["created"] += scrape_result.created
                job_totals["updated"] += scrape_result.updated
                job_totals["unchanged"] += scrape_result.unchanged
                if scrape_result.status == "failed":
                    has_failures = True
                    failed_sources += 1
                logger.info(
                    "Import %s for %s",
                    scrape_result.status,
                    source.name,
                    extra={"context": scrape_result.model_dump(mode="json")},
                )
            except Exception as error:
                if source_unavailable(error):
                    skipped_sources += 1
                    logger.warning(
                        "Skipped %s until the next run: %s",
                        source.name,
                        skip_reason(f"{type(error).__name__}: {failure_reason(error)}"),
                        extra={"context": {"source": source.name, "event": "skipped"}},
                    )
                    continue
                has_failures = True
                failed_sources += 1
                if live_status is not None:
                    live_status.record_error(f"{source.name}: {error}")
                logger.exception(
                    "Import failed for %s",
                    source.name,
                    extra={"context": {"source": source.name}},
                )
        logger.log(
            logging.WARNING if has_failures else logging.INFO,
            "Import batch finished: %s sources, %s failed, %s skipped, %s new jobs",
            len(selected_sources),
            failed_sources,
            skipped_sources,
            job_totals["created"],
            extra={
                "context": {
                    "event": "failed" if has_failures else "completed",
                    "sources": len(selected_sources),
                    "failed_sources": failed_sources,
                    "skipped_sources": skipped_sources,
                    "duration_seconds": round(time.monotonic() - started_at_monotonic, 1),
                    **job_totals,
                },
            },
        )
        exit_code = 1 if has_failures else 0
    except Timeout:
        message = "Another importer is already running for this database."
        if live_status is not None:
            live_status.record_error(message)
        logger.warning(message)
        exit_code = 2
    except Exception as error:
        if live_status is not None:
            live_status.record_error(f"Import failed: {error}")
        logger.exception("Import failed")
    finally:
        try:
            if live_status is not None:
                live_status.finish(exit_code)
            if engine is not None and os.environ.get("JOB_DISCORD_DAILY_SUPERVISED") != "1":
                publish_daily_jobs(
                    settings.daily_jobs_target(),
                    database_path,
                    started_at,
                    time.time(),
                )
        finally:
            ownership.close()
            shutdown_logging()
            if engine is not None:
                engine.dispose()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
