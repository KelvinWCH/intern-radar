import hashlib
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from datetime import time as day_time
from pathlib import Path
from threading import Event, Thread
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx2
from filelock import FileLock
from pydantic import JsonValue, TypeAdapter

from job_backend.common.discord import send_report_page
from job_backend.common.discord_gateway import DiscordGateway
from job_backend.common.logger import get_logger
from job_backend.common.models import DailyJobsTarget
from job_backend.matching.views import match_views
from job_backend.persistence.database import Database, make_engine
from job_backend.persistence.session import Session
from job_backend.scrape.daily_message import (
    EPHEMERAL,
    Score,
    company_list,
    daily_page,
    parse_custom_id,
)
from job_backend.scrape.daily_report import daily_report_html
from job_backend.scrape.models import JobReportItem
from job_backend.scrape.notifications import jobs_for_report
from job_backend.scrape.utils.constants import PROJECT_URL
from job_backend.scrape.worker.models import DailyMessageState

logger = get_logger(__name__)
API = "https://discord.com/api/v10"
_USER_AGENT = f"DiscordBot ({PROJECT_URL}, 0.1)"
_OBJECT = TypeAdapter(dict[str, JsonValue])
_INTERACTION_TOKEN = re.compile(r"[A-Za-z0-9._-]{1,500}")


def day_bounds(day: date, timezone: str) -> tuple[int, int]:
    zone = ZoneInfo(timezone)
    return (
        int(datetime.combine(day, day_time(), zone).timestamp()),
        int(datetime.combine(day + timedelta(days=1), day_time(), zone).timestamp()),
    )


def day_listings(
    engine: Database, day: date, timezone: str
) -> tuple[list[JobReportItem], dict[str, Score]]:
    start, end = day_bounds(day, timezone)
    jobs = jobs_for_report(engine, None, start, end)
    try:
        with Session(engine, read_only=True) as session:
            views = match_views(session, [job.id for job in jobs])
    except Exception as error:
        logger.info("Daily jobs %s match scores unavailable (%s)", day, type(error).__name__)
        views = {}
    return jobs, {key: (view.score, view.band) for key, view in views.items()}


def _error_code(response: httpx2.Response) -> JsonValue:
    try:
        return _OBJECT.validate_json(response.content).get("code")
    except ValueError:
        return None


def _message_id(response: httpx2.Response) -> str:
    message_id = _OBJECT.validate_json(response.content).get("id")
    if not isinstance(message_id, str) or not message_id.isascii() or not message_id.isdigit():
        raise ValueError("Discord did not return a valid daily message ID")
    return message_id


def _failure(error: Exception) -> str:
    if isinstance(error, httpx2.HTTPStatusError):
        code = _error_code(error.response)
        return f"HTTP {error.response.status_code}" + (
            f", Discord code {code}" if isinstance(code, int) else ""
        )
    return type(error).__name__


class DailyJobsPublisher:
    def __init__(
        self,
        target: DailyJobsTarget,
        database: Path,
        *,
        transport: httpx2.BaseTransport | None = None,
        wait: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.target = target
        self.transport = transport
        self.wait = wait
        self.clock = clock
        webhook = target.webhook_url.get_secret_value() if target.webhook_url else ""
        destination = target.channel_id or urlsplit(webhook).path.split("/")[-2]
        mode = "bot" if target.interactive else "webhook"
        identity = hashlib.sha256(
            f"components-v2|{mode}|{destination}|{target.timezone}".encode()
        ).hexdigest()[:24]
        self.directory = database.parent / "discord-daily-jobs" / identity

    def _client(self) -> httpx2.Client:
        headers = {"User-Agent": _USER_AGENT}
        if self.target.bot_token is not None:
            headers["Authorization"] = "Bot " + self.target.bot_token.get_secret_value()
        return httpx2.Client(
            timeout=15, follow_redirects=False, transport=self.transport, headers=headers
        )

    def _channel(self, client: httpx2.Client) -> str:
        if self.target.channel_id is not None:
            return self.target.channel_id
        if self.target.webhook_url is None:
            raise ValueError("The daily jobs bot needs a channel ID or a daily webhook")
        response = client.get(self.target.webhook_url.get_secret_value())
        response.raise_for_status()
        channel = _OBJECT.validate_json(response.content).get("channel_id")
        if not isinstance(channel, str) or not channel.isascii() or not channel.isdigit():
            raise ValueError("Discord did not return the daily webhook's channel")
        return channel

    def publish(self, engine: Database, day: date, *, create: bool = True) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{day.isoformat()}.json"
        with FileLock(str(path) + ".lock", timeout=1):
            state = (
                DailyMessageState.model_validate_json(path.read_bytes())
                if path.exists()
                else DailyMessageState()
            )
            if state.create_pending and state.message_id is None:
                logger.warning(
                    "Daily jobs %s has an unconfirmed Discord create; check the channel before "
                    "repairing its saved message ID in %s",
                    day,
                    path,
                )
                return
            jobs, scores = day_listings(engine, day, self.target.timezone)
            now = int(self.clock())
            with self._client() as client:
                attachment: tuple[str, bytes, str] | None = None
                payload: dict[str, JsonValue]
                parts: list[dict[str, JsonValue]] = []
                if self.target.interactive:
                    payload = daily_page(jobs, scores, day=day, updated_at=now)
                    create_url = f"{API}/channels/{self._channel(client)}/messages"
                    message_prefix = f"{create_url}/"
                    params: dict[str, str] = {}
                else:
                    if self.target.webhook_url is None:
                        raise ValueError("The daily jobs list needs a webhook or a bot token")
                    filename = f"daily-jobs-{day.isoformat()}.html"
                    first, *rest = company_list(
                        jobs,
                        day=day,
                        timezone=self.target.timezone,
                        updated_at=now,
                        attachment=filename,
                    )
                    payload = {
                        "username": "Intern Radar Daily Jobs",
                        **first,
                        "attachments": [{"id": 0, "filename": filename}],
                    }
                    parts = [{"username": "Intern Radar Daily Jobs", **part} for part in rest]
                    attachment = (
                        filename,
                        daily_report_html(jobs, day, self.target.timezone),
                        "text/html; charset=utf-8",
                    )
                    create_url = self.target.webhook_url.get_secret_value()
                    message_prefix = f"{create_url}/messages/"
                    params = {"wait": "true", "with_components": "true"}
                if state.message_id is not None:
                    response = send_report_page(
                        client,
                        message_prefix + state.message_id,
                        payload,
                        method="PATCH",
                        attachment=attachment,
                        wait=self.wait,
                        params=params,
                    )
                    if response.status_code != 404 or _error_code(response) != 10008:
                        response.raise_for_status()
                        self._publish_parts(
                            client, path, state, parts, create_url, message_prefix, params, create
                        )
                        return
                    state.message_id = None
                    self._save(path, state)
                if not create:
                    logger.info("Daily jobs %s message will be created on the next run", day)
                    return
                self._delete_parts(client, path, state, message_prefix)
                state.create_pending = True
                self._save(path, state)
                response = send_report_page(
                    client,
                    create_url,
                    payload,
                    attachment=attachment,
                    wait=self.wait,
                    params=params,
                )
                if 400 <= response.status_code < 500 and response.status_code != 408:
                    state.create_pending = False
                    self._save(path, state)
                response.raise_for_status()
                state.message_id = _message_id(response)
                state.create_pending = False
                self._save(path, state)
                self._publish_parts(
                    client, path, state, parts, create_url, message_prefix, params, create
                )

    def _publish_parts(
        self,
        client: httpx2.Client,
        path: Path,
        state: DailyMessageState,
        parts: list[dict[str, JsonValue]],
        create_url: str,
        message_prefix: str,
        params: dict[str, str],
        create: bool,
    ) -> None:
        for index, part in enumerate(parts):
            if index < len(state.part_ids):
                response = send_report_page(
                    client,
                    message_prefix + state.part_ids[index],
                    part,
                    method="PATCH",
                    wait=self.wait,
                    params=params,
                )
                if response.status_code != 404 or _error_code(response) != 10008:
                    response.raise_for_status()
                    continue
                self._delete_parts(client, path, state, message_prefix, keep=index)
            if not create:
                return
            response = send_report_page(client, create_url, part, wait=self.wait, params=params)
            response.raise_for_status()
            state.part_ids.append(_message_id(response))
            self._save(path, state)
        self._delete_parts(client, path, state, message_prefix, keep=len(parts))

    def _delete_parts(
        self,
        client: httpx2.Client,
        path: Path,
        state: DailyMessageState,
        message_prefix: str,
        *,
        keep: int = 0,
    ) -> None:
        for message_id in state.part_ids[keep:]:
            response = client.delete(message_prefix + message_id)
            if response.status_code != 404:
                response.raise_for_status()
        if len(state.part_ids) > keep:
            state.part_ids = state.part_ids[:keep]
            self._save(path, state)

    @staticmethod
    def _save(path: Path, state: DailyMessageState) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(state.model_dump_json(), encoding="utf-8")
        temporary.replace(path)


class DailyJobsInteractions:
    def __init__(
        self,
        target: DailyJobsTarget,
        engine: Database,
        *,
        transport: httpx2.BaseTransport | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.target = target
        self.engine = engine
        self.transport = transport
        self.clock = clock

    def handle(self, interaction: dict[str, JsonValue]) -> None:
        data = interaction.get("data")
        identifier = interaction.get("id")
        token = interaction.get("token")
        if (
            interaction.get("type") != 3
            or not isinstance(data, dict)
            or not isinstance(identifier, str)
            or not identifier.isascii()
            or not identifier.isdigit()
            or not isinstance(token, str)
            or _INTERACTION_TOKEN.fullmatch(token) is None
        ):
            return
        custom_id = data.get("custom_id")
        values = data.get("values")
        choices = (
            [value for value in values if isinstance(value, str)]
            if isinstance(values, list)
            else []
        )
        request = parse_custom_id(custom_id, choices) if isinstance(custom_id, str) else None
        if request is None:
            return
        day, view, page = request
        answer: dict[str, JsonValue]
        try:
            jobs, scores = day_listings(self.engine, day, self.target.timezone)
            answer = {
                "type": 7,
                "data": daily_page(
                    jobs, scores, day=day, view=view, page=page, updated_at=int(self.clock())
                ),
            }
        except Exception as error:
            logger.warning("Daily jobs %s page unavailable (%s)", day, type(error).__name__)
            answer = {
                "type": 4,
                "data": {
                    "flags": EPHEMERAL,
                    "content": "That page could not be loaded. Try again in a moment.",
                    "allowed_mentions": {"parse": []},
                },
            }
        try:
            with httpx2.Client(
                timeout=5,
                follow_redirects=False,
                transport=self.transport,
                headers={"User-Agent": _USER_AGENT},
            ) as client:
                client.post(
                    f"{API}/interactions/{identifier}/{token}/callback", json=answer
                ).raise_for_status()
        except httpx2.HTTPError as error:
            logger.warning("Daily jobs %s page was not delivered (%s)", day, _failure(error))


def start_daily_jobs_bot(target: DailyJobsTarget | None, database: Path) -> Callable[[], None]:
    if target is None or target.bot_token is None:
        return lambda: None
    try:
        engine = make_engine(database)
    except Exception as error:
        logger.warning("Daily jobs buttons unavailable (%s)", type(error).__name__)
        return lambda: None
    stop = Event()
    workers = ThreadPoolExecutor(max_workers=2, thread_name_prefix="discord-click")
    handler = DailyJobsInteractions(target, engine)

    def receive(interaction: dict[str, JsonValue]) -> None:
        # answer off the gateway thread so heartbeats stay on time
        workers.submit(handler.handle, interaction)

    gateway = DiscordGateway(target.bot_token, receive)
    thread = Thread(target=gateway.run, args=(stop,), name="discord-gateway", daemon=True)
    thread.start()

    def close() -> None:
        stop.set()
        thread.join(timeout=10)
        workers.shutdown(wait=True, cancel_futures=True)
        engine.dispose()

    return close


def publish_daily_jobs(
    target: DailyJobsTarget | None,
    database: Path,
    started_at: float,
    finished_at: float,
    *,
    create: bool = True,
) -> None:
    if target is None:
        return
    engine: Database | None = None
    try:
        zone = ZoneInfo(target.timezone)
        day = datetime.fromtimestamp(started_at, zone).date()
        last = datetime.fromtimestamp(finished_at, zone).date()
        engine = make_engine(database)
        publisher = DailyJobsPublisher(target, database)
        while day <= last:
            try:
                publisher.publish(engine, day, create=create)
            except Exception as error:
                logger.warning("Daily jobs %s delivery failed (%s)", day, _failure(error))
            day += timedelta(days=1)
    except Exception as error:
        logger.warning("Daily jobs delivery unavailable (%s)", type(error).__name__)
    finally:
        if engine is not None:
            engine.dispose()
