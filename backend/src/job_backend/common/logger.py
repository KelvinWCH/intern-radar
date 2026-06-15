import atexit
import copy
import logging
import math
import sys
import time
from logging.handlers import QueueHandler, QueueListener
from queue import Full, Queue
from threading import RLock

import httpx2
from pydantic import JsonValue, SecretStr, TypeAdapter

from job_backend.common.discord import log_payload
from job_backend.common.models import LogEntry, LoggingSettings, LogLevel
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session

_CONTEXT = TypeAdapter(dict[str, JsonValue])
_CONFIGURATION_LOCK = RLock()
_runtime: "_LoggingRuntime | None" = None


def _report_failure(message: str) -> None:
    try:
        sys.stderr.write(f"Logging: {message}\n")
    except (OSError, ValueError):
        pass


class _DatabaseHandler(logging.Handler):
    def __init__(self, engine: Database) -> None:
        super().__init__()
        self.engine = engine
        self.retry_at = 0.0

    def emit(self, record: logging.LogRecord) -> None:
        if time.monotonic() < self.retry_at:
            return
        try:
            with Session(self.engine) as session, session.begin():
                session.add(
                    LogEntry(
                        created_at=record.created,
                        level=record.levelname,
                        logger=record.name,
                        message=record.getMessage(),
                        exception=record.exc_text,
                        pathname=record.pathname,
                        line_number=record.lineno,
                        process_id=record.process,
                        thread_name=record.threadName,
                        context=_CONTEXT.validate_python(getattr(record, "context", {})),
                    )
                )
        except Exception as error:
            self.retry_at = time.monotonic() + 60
            _report_failure(
                f"Database write failed ({type(error).__name__}); writes paused for 60s. "
                "Console and Discord output retained."
            )


class _DiscordHandler(logging.Handler):
    def __init__(
        self,
        webhook: SecretStr,
        level: LogLevel,
        transport: httpx2.BaseTransport | None,
    ) -> None:
        super().__init__(level)
        self.webhook = webhook
        self.client = httpx2.Client(timeout=5, follow_redirects=False, transport=transport)
        self.retry_at = 0.0

    def emit(self, record: logging.LogRecord) -> None:
        if time.monotonic() < self.retry_at:
            return
        try:
            response = self.client.post(
                self.webhook.get_secret_value(), params={"wait": "true"}, json=log_payload(record)
            )
            if response.status_code == 429:
                try:
                    delay = float(response.headers.get("Retry-After", "60"))
                except ValueError:
                    delay = 60.0
                self.retry_at = time.monotonic() + (
                    max(1.0, delay) if math.isfinite(delay) else 60.0
                )
                _report_failure(
                    "Discord rate limited; remaining notifications skipped during its cooldown."
                )
                return
            response.raise_for_status()
        except Exception as error:
            self.retry_at = time.monotonic() + 60
            _report_failure(
                f"Discord delivery failed ({type(error).__name__}); notifications paused for 60s."
            )

    def close(self) -> None:
        self.client.close()
        super().close()


class _BackgroundHandler(QueueHandler):
    def __init__(self, queue: Queue[logging.LogRecord | None]) -> None:
        super().__init__(queue)
        self.overflow_reported = False

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        prepared = copy.copy(record)
        prepared.msg = record.getMessage()
        prepared.args = None
        if record.exc_info:
            prepared.exc_text = logging.Formatter().formatException(record.exc_info)
        prepared.exc_info = None
        try:
            context = _CONTEXT.validate_python(getattr(record, "context", {}), strict=True)
            prepared.context = copy.deepcopy(context)
        except ValueError:
            prepared.context = {}
            _report_failure("Tracking context must be a JSON object; storing an empty context.")
        return prepared

    def enqueue(self, record: logging.LogRecord) -> None:
        try:
            self.queue.put_nowait(record)
            self.overflow_reported = False
        except Full:
            if not self.overflow_reported:
                _report_failure("Background queue full; additional records kept only on console.")
                self.overflow_reported = True

    def handleError(self, record: logging.LogRecord) -> None:
        _report_failure("Could not prepare a background log record.")


class _DrainingListener(QueueListener):
    def __init__(
        self, records: Queue[logging.LogRecord | None], *handlers: logging.Handler
    ) -> None:
        super().__init__(records, *handlers, respect_handler_level=True)
        self.records = records

    def enqueue_sentinel(self) -> None:
        self.records.put(None)


class _LoggingRuntime:
    def __init__(
        self,
        settings: LoggingSettings,
        engine: Database | None,
        transport: httpx2.BaseTransport | None,
    ) -> None:
        self.logger = logging.getLogger("job_backend")
        self.previous_level = self.logger.level
        self.previous_propagate = self.logger.propagate
        self.handlers: list[logging.Handler] = []
        self.destinations: list[logging.Handler] = []
        self.listener: _DrainingListener | None = None
        formatter = logging.Formatter("%(asctime)sZ %(levelname)s %(name)s: %(message)s")
        formatter.converter = time.gmtime
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(settings.level)
        console.setFormatter(formatter)
        self.handlers.append(console)
        if settings.discord_webhook_url is not None:
            discord = _DiscordHandler(
                settings.discord_webhook_url, settings.discord_level, transport
            )
            discord.setFormatter(formatter)
            self.destinations.append(discord)
        if engine is not None and settings.database_enabled:
            self.destinations.append(_DatabaseHandler(engine))
        if self.destinations:
            queue: Queue[logging.LogRecord | None] = Queue(maxsize=1000)
            background = _BackgroundHandler(queue)
            background.setLevel(settings.level)
            self.handlers.append(background)
            self.listener = _DrainingListener(queue, *self.destinations)
            self.listener.start()
        self.logger.setLevel(settings.level)
        self.logger.propagate = False
        for handler in self.handlers:
            self.logger.addHandler(handler)

    def close(self) -> None:
        for handler in self.handlers:
            self.logger.removeHandler(handler)
        if self.listener is not None:
            self.listener.stop()
        for handler in (*self.handlers, *self.destinations):
            handler.close()
        self.logger.setLevel(self.previous_level)
        self.logger.propagate = self.previous_propagate


def get_logger(name: str = "job_backend") -> logging.Logger:
    if name != "job_backend" and not name.startswith("job_backend."):
        name = f"job_backend.{name}"
    return logging.getLogger(name)


def configure_logging(
    *,
    engine: Database | None = None,
    settings: LoggingSettings | None = None,
    discord_transport: httpx2.BaseTransport | None = None,
) -> None:
    global _runtime
    resolved = settings if settings is not None else LoggingSettings.from_environment()
    with _CONFIGURATION_LOCK:
        shutdown_logging()
        _runtime = _LoggingRuntime(resolved, engine, discord_transport)


def shutdown_logging() -> None:
    global _runtime
    with _CONFIGURATION_LOCK:
        if _runtime is not None:
            _runtime.close()
            _runtime = None


atexit.register(shutdown_logging)
