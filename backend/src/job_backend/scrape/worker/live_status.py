import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Lock, Thread

import httpx2
from pydantic import JsonValue, SecretStr, TypeAdapter

from job_backend.common.discord import (
    error_summary,
    safe_text,
    send_report_page,
)
from job_backend.common.logger import get_logger
from job_backend.persistence.database import Database, make_engine
from job_backend.persistence.session import Session
from job_backend.scrape.models import ScrapeEvent, ScrapeRun, ScrapeTrigger
from job_backend.scrape.utils.source_skips import SKIPPED_PHASES, skip_reason
from job_backend.scrape.worker.constants import OUTCOME_LABELS, STAGE_LABELS

logger = get_logger(__name__)


def _duration(seconds: float) -> str:
    total = max(0, int(seconds))
    if total < 60:
        return f"{total}s"
    if total < 3600:
        return f"{total // 60}m {total % 60}s"
    return f"{total // 3600}h {total % 3600 // 60}m"


def _bar(done: int, total: int, width: int = 16) -> str:
    filled = round(width * max(0.0, min(1.0, done / total))) if total else 0
    return "▓" * filled + "░" * (width - filled)


class LiveStatus:
    def __init__(
        self,
        webhook: SecretStr,
        database: Path,
        group: str,
        *,
        transport: httpx2.BaseTransport | None = None,
        clock: float | None = None,
        trigger: ScrapeTrigger = "cron",
        sources: set[str] | None = None,
    ) -> None:
        self.webhook = webhook
        self.database = database
        self.group = group
        self.trigger = trigger
        self.sources = sources
        self.started = time.time() if clock is None else clock
        self.client = httpx2.Client(timeout=5, follow_redirects=False, transport=transport)
        self.message_id: str | None = None
        self.engine: Database | None = None
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self._lock = Lock()
        self._stop = Event()
        self._thread: Thread | None = None
        self._started = False
        self._finished = False

    def start(self, *, background: bool = False) -> None:
        if self._started:
            return
        self._started = True
        try:
            response = self.client.post(
                self.webhook.get_secret_value(),
                params={"wait": "true"},
                json=self._payload("Scraping " + self.group, 0xC6A0F6, final=False),
            )
            response.raise_for_status()
            body = TypeAdapter(dict[str, JsonValue]).validate_json(response.content)
            message_id = body.get("id")
            if (
                not isinstance(message_id, str)
                or not message_id.isascii()
                or not message_id.isdigit()
            ):
                raise ValueError("Discord did not return a valid message ID")
            self.message_id = message_id
        except Exception as error:
            logger.warning("Discord live status unavailable (%s)", type(error).__name__)
        if background and self.message_id is not None:
            self._thread = Thread(target=self._refresh, name="scrape-discord-status", daemon=True)
            self._thread.start()

    def _refresh(self) -> None:
        while not self._stop.wait(15):
            self.update()

    def record_error(self, message: str) -> None:
        with self._lock:
            self.errors.append(safe_text(error_summary(message), 300))
            self.errors = self.errors[-6:]

    def record_warning(self, message: str) -> None:
        with self._lock:
            self.warnings.append(safe_text(message, 300))
            self.warnings = self.warnings[-6:]

    def update(self) -> None:
        with self._lock:
            if not self._finished:
                self._edit(self._payload("Scraping " + self.group, 0xC6A0F6, final=False))

    def finish(self, code: int) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        if self._finished:
            return
        self._finished = True
        title, color = OUTCOME_LABELS.get(code, ("Scrape finished with errors", 0xED8796))
        try:
            if self.message_id is None:
                return
            snapshot = self._runs()
            summary = self._payload(title, color, final=True, code=code, snapshot=snapshot)
            self._edit(summary)
        except Exception as error:
            logger.warning("Discord scrape report delivery failed (%s)", type(error).__name__)
        finally:
            self.client.close()
            if self.engine is not None:
                self.engine.dispose()

    def _edit(self, payload: dict[str, JsonValue]) -> None:
        if self.message_id is None:
            return
        try:
            response = send_report_page(
                self.client,
                f"{self.webhook.get_secret_value()}/messages/{self.message_id}",
                payload,
                method="PATCH",
            )
            response.raise_for_status()
        except Exception as error:
            logger.warning("Discord live status update failed (%s)", type(error).__name__)

    def _runs(self) -> tuple[list[ScrapeRun], list[ScrapeEvent]]:
        try:
            if self.engine is None:
                self.engine = make_engine(self.database)
            with Session(self.engine) as session:
                runs = list(
                    session.find(
                        ScrapeRun,
                        equal={"trigger": self.trigger},
                        interval=("started_at", self.started, None),
                        where=lambda run: self.sources is None or run.source in self.sources,
                        order_by=("started_at", "id"),
                    )
                )
                run_ids: list[JsonValue] = list(sorted({run.id for run in runs}))
                events = list(
                    reversed(
                        session.filtered_recent(
                            ScrapeEvent,
                            "created_at",
                            limit=6,
                            one_of=("run_id", run_ids),
                        )
                    )
                )
                issues = [
                    event
                    for level in ("warning", "error")
                    for event in session.filtered_recent(
                        ScrapeEvent,
                        "created_at",
                        limit=6,
                        equal={"level": level},
                        one_of=("run_id", run_ids),
                    )
                ]
                events = sorted(
                    {event.id: event for event in [*events, *issues]}.values(),
                    key=lambda event: (event.created_at, event.id),
                )
                session.expunge_all()
                return runs, events
        except Exception:
            return [], []

    def _payload(
        self,
        title: str,
        color: int,
        *,
        final: bool,
        code: int | None = None,
        snapshot: tuple[list[ScrapeRun], list[ScrapeEvent]] | None = None,
    ) -> dict[str, JsonValue]:
        runs, events = self._runs() if snapshot is None else snapshot
        skipped_runs = [
            run for run in runs if run.status == "failed" and run.phase in SKIPPED_PHASES
        ]
        skipped_ids = {run.id for run in skipped_runs}
        failed_runs = [
            run
            for run in runs
            if run.id not in skipped_ids and (run.status == "failed" or run.error)
        ]
        warnings = [event for event in events if event.level == "warning"]
        errors = [event for event in events if event.level == "error"]
        failure_count = sum(
            count
            for run in runs
            if run.performance is not None
            and isinstance(count := run.performance.get("failure_count"), int)
        )
        has_errors = bool(errors or self.errors or failed_runs)
        has_warnings = bool(
            warnings or self.warnings or skipped_runs or (failure_count and not has_errors)
        )
        if has_errors:
            color = 0xED8796
            if final and code == 0:
                title = "Scrape complete with errors"
        elif has_warnings and code in {None, 0}:
            color = 0xEED49F
            if final and code == 0:
                title = "Scrape complete with warnings"
        running = next((run for run in reversed(runs) if run.status == "running"), None)
        elapsed = max(0.0, time.time() - self.started)
        lines: list[str] = [
            f"**{safe_text(self.group, 120).title()}** · "
            + ("Final results" if final else "Live progress")
        ]
        if running is not None and not final:
            stage = STAGE_LABELS.get(running.phase or "", running.phase or "Working")
            lines.append(f"**Now:** {safe_text(stage, 120)} · `{safe_text(running.source, 120)}`")
            if running.items_total:
                done, total = running.items_done or 0, running.items_total
                percent = min(100, max(0, round(done / total * 100)))
                lines.append(
                    f"`{_bar(done, total)}` **{percent}%** · {done:,} / {total:,} postings"
                )
        elif not final:
            lines.append("**Now:** Starting the importer…")
        if has_errors or has_warnings:
            issues = [
                label
                for present, label in ((has_errors, "errors"), (has_warnings, "warnings"))
                if present
            ]
            lines.append(
                "**Issues:** "
                + " and ".join(issues)
                + " recorded"
                + (f" · {failure_count:,} scrape issues" if failure_count else "")
                + (
                    ". See details below and the local logs."
                    if final
                    else ". Continuing with remaining work."
                )
            )
        finished = sum(run.status in {"completed", "not_modified"} for run in runs)
        failed = sum(run.status == "failed" for run in failed_runs)
        fetched = sum(run.fetched for run in runs)
        matched = sum(run.matched for run in runs)
        checked = sum(run.items_done or 0 for run in runs)
        input_tokens = sum(run.input_tokens or 0 for run in runs)
        output_tokens = sum(run.output_tokens or 0 for run in runs)
        fields: list[JsonValue] = [
            {
                "name": "New jobs",
                "value": f"**{sum(run.created for run in runs):,}**",
                "inline": True,
            },
            {
                "name": "Updated",
                "value": f"**{sum(run.updated for run in runs):,}**",
                "inline": True,
            },
            {
                "name": "Unchanged",
                "value": f"**{sum(run.unchanged for run in runs):,}**",
                "inline": True,
            },
            {
                "name": "Discovery",
                "value": f"{fetched:,} found\n{matched:,} matched"
                + (f" · {matched / fetched:.0%} yield" if fetched else ""),
                "inline": True,
            },
            {
                "name": "Sources",
                "value": f"{finished:,} finished · {len(skipped_runs):,} skipped · "
                f"{failed:,} failed\n"
                f"{sum(run.status == 'running' for run in runs):,} "
                + ("unfinished" if final else "active"),
                "inline": True,
            },
            {
                "name": "Pace",
                "value": f"{_duration(elapsed)} elapsed\n{checked:,} postings checked"
                + (f" · {checked / elapsed * 60:.1f}/min" if elapsed >= 1 and checked else ""),
                "inline": True,
            },
            {
                "name": "AI usage",
                "value": f"{input_tokens + output_tokens:,} tokens\n"
                f"{input_tokens:,} in · {output_tokens:,} out",
                "inline": True,
            },
            {"name": "Started", "value": f"<t:{int(self.started)}:R>", "inline": True},
        ]
        if code is not None and code != 0:
            reason = {
                124: "The scrape reached its time limit.",
                130: "The scrape was stopped.",
            }.get(
                code, "Some work could not finish. See the source errors below or the local logs."
            )
            lines.append(f"```text\n{reason} (exit {code})\n```")
        failures = [
            f"{safe_text(run.source, 100)}: {error_summary(run.error)}"
            for run in failed_runs
            if run.error
        ]
        failures.extend(self.errors)
        failures.extend(error_summary(event.message) for event in errors)
        if failures:
            fields.append(
                {
                    "name": "Errors",
                    "value": "```text\n"
                    + safe_text("\n".join(dict.fromkeys(failures)), 450)
                    + "\n```",
                    "inline": False,
                }
            )
        notices = [
            safe_text(run.error or "", 300)
            if run.phase == "timeout"
            else f"Skipped {safe_text(run.source, 100)}: {skip_reason(run.error or '')}"
            for run in skipped_runs
        ]
        notices.extend(self.warnings)
        notices.extend(
            error_summary(event.message) for event in warnings if event.run_id not in skipped_ids
        )
        if notices:
            fields.append(
                {
                    "name": "Warnings",
                    "value": "```text\n"
                    + safe_text("\n".join(dict.fromkeys(notices)), 450)
                    + "\n```",
                    "inline": False,
                }
            )
        if events:
            steps = "\n".join(
                ("! " if event.level != "info" else "> ")
                + safe_text(
                    error_summary(event.message)
                    if event.level in {"error", "warning"}
                    and not event.message.startswith("Skipped ")
                    else event.message,
                    140,
                )
                for event in events[-6:]
            )
            fields.append(
                {
                    "name": "Latest steps",
                    "value": "```text\n" + safe_text(steps, 450) + "\n```",
                    "inline": False,
                }
            )
        return {
            "username": "Intern Radar Scraper",
            "allowed_mentions": {"parse": []},
            "embeds": [
                {
                    "title": safe_text(title, 256),
                    "description": "\n".join(lines)[:4000],
                    "color": color,
                    "fields": fields,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "footer": {
                        "text": "Intern Radar • final" if final else "Intern Radar • updates live"
                    },
                }
            ],
        }
