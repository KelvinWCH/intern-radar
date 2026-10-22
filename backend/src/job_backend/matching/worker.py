import time
from collections.abc import Callable
from pathlib import Path
from threading import Event

from job_backend.common.logger import get_logger
from job_backend.jobs.identity_refresh import refresh_identities
from job_backend.matching.constants import CHECK_INTERVAL_SECONDS
from job_backend.matching.embedding import Embedder, embedder_from_environment
from job_backend.matching.service import MatchService
from job_backend.persistence.database import Database, make_engine, migrate

logger = get_logger(__name__)

FAILURE_BACKOFF = 10


class MatchMaintenance:
    def __init__(
        self,
        database: Path,
        stop: Event,
        *,
        engine_factory: Callable[[Path], Database] | None = None,
        embedder_factory: Callable[[], Embedder] | None = None,
        interval: float = CHECK_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.database = database
        self.stop = stop
        self.engine_factory = engine_factory or self._open
        self.embedder_factory = embedder_factory or (
            lambda: embedder_from_environment(database.parent)
        )
        self.interval = interval
        self.clock = clock
        self._service: MatchService | None = None
        self._identities_refreshed = False
        self._next_check = 0.0
        self._last_error: str | None = None

    @staticmethod
    def _open(database: Path) -> Database:
        engine = make_engine(database)
        migrate(engine)
        return engine

    def __call__(self, *, after_batch: bool) -> None:
        now = self.clock()
        if self.stop.is_set() or (not after_batch and now < self._next_check):
            return
        self._next_check = now + self.interval
        try:
            if self._service is None:
                self._service = MatchService(
                    self.engine_factory(self.database),
                    self.embedder_factory,
                    should_stop=self.stop.is_set,
                )
            if not self._identities_refreshed:
                rekeyed = refresh_identities(self._service.engine)
                self._identities_refreshed = True
                if rekeyed:
                    logger.info("Related-posting keys refreshed for %s jobs", rekeyed)
            run = self._service.refresh()
        except Exception as error:
            message = f"{type(error).__name__}: {error}"
            self._next_check = now + self.interval * FAILURE_BACKOFF
            if message != self._last_error:
                # only log the same failure once
                logger.warning("Job matching pass failed; retrying later: %s", message)
                self._last_error = message
            return
        self._last_error = None
        if run.embedded or run.scored:
            logger.info(
                "Job matching: embedded %s, scored %s%s on %s",
                run.embedded,
                run.scored,
                f", {run.pending} still to embed" if run.pending else "",
                run.device or "no model",
            )
        if run.pending:
            self._next_check = now
