import argparse
import json
import signal
from functools import partial
from threading import Event
from types import FrameType

from filelock import Timeout

from job_backend.common.discord import alert_user_id
from job_backend.common.logger import configure_logging, get_logger, shutdown_logging
from job_backend.common.models import LoggingSettings
from job_backend.matching.worker import MatchMaintenance
from job_backend.persistence.database import default_database_path
from job_backend.scrape.daily_notifications import start_daily_jobs_bot
from job_backend.scrape.health.report import DailyHealthReport
from job_backend.scrape.pipeline.models import JobPageSettings
from job_backend.scrape.utils.browser import open_browser_page
from job_backend.scrape.utils.browser_policy import unattended_browser_mode
from job_backend.scrape.utils.constants import UNATTENDED_BROWSER_ENV
from job_backend.scrape.worker.constants import GROUP_ARGUMENTS
from job_backend.scrape.worker.models import WorkerArguments
from job_backend.scrape.worker.ownership import process_lock
from job_backend.scrape.worker.runner import run_scrape_process
from job_backend.scrape.worker.scheduler import run_schedule
from job_backend.scrape.worker.settings import load_settings
from job_backend.scrape.worker.state import load_state

logger = get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run scheduled headless job imports")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--once", action="store_true", help="Run due tasks once and exit.")
    modes.add_argument(
        "--show-schedule", action="store_true", help="Print settings without running imports."
    )
    modes.add_argument(
        "--check-browser",
        action="store_true",
        help="Check local Chromium without network or AI calls.",
    )
    arguments = WorkerArguments()
    parser.parse_args(argv, namespace=arguments)
    try:
        settings = load_settings()
    except (ValueError, OSError) as error:
        parser.error(f"Invalid worker settings: {error}")
    if arguments.show_schedule:
        print(
            json.dumps(
                {
                    **settings.model_dump(mode="json"),
                    "import_arguments": GROUP_ARGUMENTS,
                    "forced_browser_settings": UNATTENDED_BROWSER_ENV,
                },
                indent=2,
            )
        )
        return 0
    try:
        configure_logging()
        if arguments.check_browser:
            with unattended_browser_mode(True):
                with open_browser_page(JobPageSettings.from_environment()) as page:
                    page.set_content("<title>Browser ready</title><p>Headless browser ready.</p>")
                    if page.title() != "Browser ready":
                        raise RuntimeError("Browser did not render the local check page")
            print(json.dumps({"browser": "ready", "headless": True, "sandbox": True}))
            return 0
        database = default_database_path()
        database.parent.mkdir(parents=True, exist_ok=True)
        stop = Event()

        def request_stop(_number: int, _frame: FrameType | None) -> None:
            stop.set()

        previous = {
            number: signal.signal(number, request_stop)
            for number in (signal.SIGINT, signal.SIGTERM)
        }
        try:
            with process_lock(database, "worker"):
                state_path = database.with_name("worker-state.json")
                state = load_state(state_path)
                logger.info("Worker started; browser imports are headless with no manual prompts")
                logging_settings = LoggingSettings.from_environment()
                webhook = logging_settings.discord_scrape_webhook_url
                try:
                    user_id = alert_user_id()
                except ValueError as error:
                    logger.warning("Scrape health reports will not mention anyone: %s", error)
                    user_id = None
                daily = logging_settings.daily_jobs_target()
                stop_bot = (
                    (lambda: None) if arguments.once else start_daily_jobs_bot(daily, database)
                )
                try:
                    return run_schedule(
                        settings,
                        state,
                        state_path,
                        stop,
                        partial(
                            run_scrape_process,
                            database=database,
                            settings=settings,
                            stop=stop,
                            webhook=webhook,
                            daily=daily,
                            status_seconds=settings.status_seconds,
                        ),
                        once=arguments.once,
                        live_status=webhook is not None,
                        idle=DailyHealthReport(
                            database,
                            settings,
                            webhook,
                            user_id=user_id,
                            idle=MatchMaintenance(database, stop),
                        ),
                    )
                finally:
                    stop_bot()
        finally:
            for number, handler in previous.items():
                signal.signal(number, handler)
    except Timeout:
        logger.warning(
            "Another worker is already using this database.", extra={"discord_scrape": True}
        )
        return 2
    except Exception:
        logger.exception("Worker failed", extra={"discord_scrape": True})
        return 1
    finally:
        shutdown_logging()


if __name__ == "__main__":
    raise SystemExit(main())
