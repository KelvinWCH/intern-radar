import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx2
from pydantic import JsonValue, SecretStr

from job_backend.common.discord import error_summary, message_pages, safe_text, send_report_page
from job_backend.common.logger import get_logger
from job_backend.persistence.database import Database, make_engine
from job_backend.persistence.session import Session
from job_backend.scrape.health.constants import EMBED_CHARACTERS, REPORT_HOUR, RETRY_SECONDS
from job_backend.scrape.health.models import HealthReportState, ScrapeHealth, ScrapeRegression
from job_backend.scrape.health.regressions import scrape_health
from job_backend.scrape.worker.models import WorkerSettings
from job_backend.scrape.worker.scheduler import IdleWork
from job_backend.scrape.worker.sources import scheduled_sources

logger = get_logger(__name__)

_SECTIONS = (
    ("failing", "Failing", 0xED8796, None),
    (
        "collapsed",
        "Listing far fewer postings than usual",
        0xEED49F,
        "A change that narrows what an adapter lists looks the same; "
        "it drops off once the new count is usual.",
    ),
    ("stopped", "Not running on schedule", 0x8AADF4, None),
)


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _when(timestamp: float | None, style: str = "R") -> str:
    return f"<t:{int(timestamp)}:{style}>" if timestamp is not None else "not this week"


def _line(finding: ScrapeRegression, new: bool) -> str:
    name = (
        f"`{safe_text(finding.source, 120)}`" if finding.source else f"The {finding.group} import"
    )
    marker = "🆕 " if new else ""
    if finding.kind == "failing":
        line = (
            f"{name} · failed {_plural(finding.runs, 'scheduled run')} in a row since "
            f"{_when(finding.since, 'f')} · last worked {_when(finding.last_worked)}"
        )
        if finding.error:
            line += f"\n  `{safe_text(error_summary(finding.error), 180)}`"
    elif finding.kind == "collapsed":
        line = (
            f"{name} · listed at most {finding.fetched:,} postings in the last day, "
            f"usually {finding.usual:,}"
        )
    else:
        line = f"{name} · no finished scheduled run since {_when(finding.since)}"
    return marker + line


def health_messages(
    health: ScrapeHealth, day: str, previous: set[str], user_id: str | None
) -> list[dict[str, JsonValue]]:
    new = [finding for finding in health.regressions if finding.key not in previous]
    summary = (
        f"**Scrape health · {day}** · {health.healthy:,} of "
        f"{_plural(health.sources, 'scheduled source')} healthy"
    )
    if new:
        summary += f" · {_plural(len(new), 'new problem')}"
    elif not health.regressions:
        summary += " · nothing regressed"
    alarming = any(finding.kind != "collapsed" for finding in new)
    mention = user_id if alarming and user_id else None
    embeds: list[dict[str, JsonValue]] = []
    for kind, title, color, note in _SECTIONS:
        lines = [
            _line(finding, finding.key not in previous)
            for finding in health.regressions
            if finding.kind == kind
        ]
        chunks: list[list[str]] = []
        for line in lines:
            if (
                not chunks
                or sum(len(item) + 1 for item in chunks[-1]) + len(line) > EMBED_CHARACTERS
            ):
                chunks.append([])
            chunks[-1].append(line)
        for chunk in chunks:
            embed: dict[str, JsonValue] = {
                "title": title,
                "description": "\n".join(chunk),
                "color": color,
            }
            if note:
                embed["footer"] = {"text": note}
            embeds.append(embed)
    pages = message_pages(
        {"username": "Intern Radar Scrape Health", "content": summary, "embeds": []}, embeds
    )
    for index, page in enumerate(pages):
        if index:
            page["content"] = f"**Scrape health · {day}** · continued"
        page["allowed_mentions"] = {"users": [mention] if mention and not index else []}
        if mention and not index:
            page["content"] = f"<@{mention}> {page['content']}"
    return pages


class DailyHealthReport:
    def __init__(
        self,
        database: Path,
        settings: WorkerSettings,
        webhook: SecretStr | None,
        *,
        user_id: str | None = None,
        idle: IdleWork | None = None,
        engine_factory: Callable[[Path], Database] = make_engine,
        transport: httpx2.BaseTransport | None = None,
        clock: Callable[[], float] = time.time,
        wait: Callable[[float], None] = time.sleep,
    ) -> None:
        self.database = database
        self.settings = settings
        self.webhook = webhook
        self.user_id = user_id
        self.idle = idle
        self.engine_factory = engine_factory
        self.transport = transport
        self.clock = clock
        self.wait = wait
        self.state_path = database.with_name("scrape-health.json")
        self._posted_day: str | None = None
        self._next_attempt = 0.0

    def __call__(self, *, after_batch: bool) -> None:
        if self.idle is not None:
            self.idle(after_batch=after_batch)
        self.publish_if_due()

    def publish_if_due(self) -> bool:
        now = self.clock()
        if self.webhook is None or now < self._next_attempt:
            return False
        local = datetime.fromtimestamp(now, ZoneInfo(self.settings.timezone))
        day = local.date().isoformat()
        if local.hour < REPORT_HOUR or self._posted_day == day:
            return False
        try:
            state = (
                HealthReportState.model_validate_json(self.state_path.read_bytes())
                if self.state_path.exists()
                else HealthReportState()
            )
            if state.day == day:
                self._posted_day = day
                return False
            engine = self.engine_factory(self.database)
            try:
                with Session(engine, read_only=True) as session:
                    health = scrape_health(session, scheduled_sources(self.settings), now)
            finally:
                engine.dispose()
            pages = health_messages(health, day, set(state.reported), self.user_id)
            with httpx2.Client(
                timeout=15, follow_redirects=False, transport=self.transport
            ) as client:
                for page in pages:
                    send_report_page(
                        client, self.webhook.get_secret_value(), page, wait=self.wait
                    ).raise_for_status()
        except Exception as error:
            self._next_attempt = now + RETRY_SECONDS
            logger.warning("Scrape health report failed; retrying later (%s)", type(error).__name__)
            return False
        saved = HealthReportState(day=day, reported=[item.key for item in health.regressions])
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(saved.model_dump_json(), encoding="utf-8")
        temporary.replace(self.state_path)
        self._posted_day = day
        logger.info(
            "Scrape health: %s of %s scheduled sources healthy, %s problems",
            health.healthy,
            health.sources,
            len(health.regressions),
        )
        return True
