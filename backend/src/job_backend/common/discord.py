import json
import logging
import math
import os
import random
import re
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from threading import Lock

import httpx2
from pydantic import JsonValue, TypeAdapter

_CONTEXT = TypeAdapter(dict[str, JsonValue])
_WEBHOOK = re.compile(
    r"https://(?:(?:canary|ptb)\.)?discord(?:app)?\.com/api/(?:v\d+/)?"
    r"webhooks/\d+/[A-Za-z0-9._-]+"
)
_FIELDS = {
    "group": "Group",
    "source": "Source",
    "sources": "Sources",
    "failed_sources": "Failed sources",
    "skipped_sources": "Skipped sources",
    "fetched": "Found",
    "matched": "Matched",
    "created": "New jobs",
    "updated": "Updated",
    "unchanged": "Unchanged",
    "duration_seconds": "Seconds",
    "interval_hours": "Every (hours)",
    "exit_code": "Exit code",
}
_TITLE_LOCK = Lock()
_LAST_TITLES: dict[str, str] = {}
_TITLES = {
    "error": (
        "Error: that did not go as planned",
        "Error: back to the logs",
        "Error: something needs a fix",
    ),
    "warning": (
        "Warning: check the details",
        "Warning: needs attention",
    ),
}


def alert_title(*, warning: bool = False) -> str:
    category = "warning" if warning else "error"
    with _TITLE_LOCK:
        title = random.choice(
            [item for item in _TITLES[category] if item != _LAST_TITLES.get(category)]
        )
        _LAST_TITLES[category] = title
    return title


def alert_user_id() -> str | None:
    value = os.environ.get("JOB_DISCORD_ALERT_USER_ID", "").strip()
    if not value:
        return None
    if re.fullmatch(r"\d{17,20}", value) is None:
        raise ValueError("JOB_DISCORD_ALERT_USER_ID must be a numeric Discord user ID")
    return value


def _clip(value: str, limit: int) -> str:
    value = _WEBHOOK.sub("[Discord webhook redacted]", value)
    return value if len(value) <= limit else value[: limit - 14] + "\n… [truncated]"


def safe_text(value: str, limit: int = 1000) -> str:
    return _clip(value.replace("`", "'"), limit)


def _embed_size(embed: dict[str, JsonValue]) -> int:
    def size(value: JsonValue) -> int:
        return len(value.encode("utf-16-le")) // 2 if isinstance(value, str) else 0

    total = sum(size(embed.get(key)) for key in ("title", "description"))
    for key, field in (("footer", "text"), ("author", "name")):
        item = embed.get(key)
        if isinstance(item, dict):
            total += size(item.get(field))
    fields = embed.get("fields")
    if isinstance(fields, list):
        total += sum(
            size(field.get("name")) + size(field.get("value"))
            for field in fields
            if isinstance(field, dict)
        )
    return total


def message_pages(
    summary: dict[str, JsonValue], embeds: Sequence[dict[str, JsonValue]]
) -> list[dict[str, JsonValue]]:
    original = summary.get("embeds", [])
    current: list[JsonValue] = list(original) if isinstance(original, list) else []
    size = sum(_embed_size(embed) for embed in current if isinstance(embed, dict))
    pages: list[dict[str, JsonValue]] = []
    for embed in embeds:
        length = _embed_size(embed)
        if current and (size + length > 6000 or len(current) >= 10):
            pages.append({**summary, "embeds": current})
            current, size = [], 0
        current.append(embed)
        size += length
    pages.append({**summary, "embeds": current})
    return pages


def send_report_page(
    client: httpx2.Client,
    url: str,
    payload: dict[str, JsonValue],
    *,
    method: str = "POST",
    wait: Callable[[float], None] = time.sleep,
    attachment: tuple[str, bytes, str] | None = None,
    params: dict[str, str] | None = None,
) -> httpx2.Response:
    query = {"wait": "true"} if params is None else params

    def send() -> httpx2.Response:
        if attachment is not None:
            return client.request(
                method,
                url,
                params=query,
                data={"payload_json": json.dumps(payload, ensure_ascii=False)},
                files={"files[0]": attachment},
            )
        return client.request(method, url, params=query, json=payload)

    response = send()
    if response.status_code != 429:
        return response
    try:
        data = _CONTEXT.validate_json(response.content)
        raw_delay = data.get("retry_after", response.headers.get("Retry-After", "60"))
        delay = float(raw_delay) if isinstance(raw_delay, str | int | float) else 60.0
    except ValueError:
        delay = 60.0
    if not math.isfinite(delay) or delay < 0 or delay > 30:
        return response
    wait(max(0.1, delay))
    return send()


def error_summary(message: str) -> str:
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    exceptions = [
        line
        for line in lines
        if re.match(r"^[\w.]+(?:Error|Exception|Timeout|Failure|Interrupt):", line)
    ]
    detail = (
        exceptions[-1] if exceptions else (lines[-1] if lines else "No error detail was recorded.")
    )
    lower = detail.lower()
    http_status = re.search(
        r"(?:HTTP(?:StatusError)?[: /]*|status(?: code)?[: =]*|"
        r"(?:client|server) error ['\"])(\d{3})\b",
        detail,
        re.IGNORECASE,
    )
    status = http_status.group(1) if http_status else None
    if "10013" in detail:
        return (
            "Windows blocked a network connection (WinError 10013). "
            "Check this process's network permissions and firewall rules."
        )
    if "10061" in detail or "connection refused" in lower:
        return (
            "The destination refused the connection. Check that the service is running "
            "and its host and port are correct."
        )
    if "timeout" in lower or "timed out" in lower:
        return (
            "The service did not respond before the time limit. Try again; "
            "if it keeps happening, check the service or increase the timeout."
        )
    if status == "429":
        return (
            "The service is receiving requests too quickly (HTTP 429). "
            "Wait before trying again or reduce concurrency."
        )
    if status == "401":
        return (
            "The service rejected the credentials (HTTP 401). "
            "Check the configured API key or sign-in."
        )
    if status == "403":
        return (
            "The service denied access (HTTP 403). "
            "Check permissions or whether the site is blocking automated requests."
        )
    if status in {"500", "502", "503", "504"}:
        return "The remote service could not handle the request. Try again after it recovers."
    if "jsondecodeerror" in lower:
        return (
            "The service returned content that could not be read as JSON. "
            "It may have returned an error page instead of data."
        )
    if "filenotfounderror" in lower:
        return "A required file or executable could not be found. " + safe_text(
            detail.partition(":")[2].strip(), 600
        )
    if "connecterror" in lower or "connectionerror" in lower:
        return "Could not connect to the service. " + safe_text(
            detail.partition(":")[2].strip(), 600
        )
    detail = re.sub(r"^[\w.]+(?:Error|Exception|Failure):\s*", "", detail)
    return safe_text(detail, 1000)


def log_payload(record: logging.LogRecord) -> dict[str, JsonValue]:
    scrape = getattr(record, "discord_scrape", False) is True
    if record.levelno >= logging.ERROR:
        title, color = alert_title(), 0xED8796
    elif record.levelno >= logging.WARNING:
        title, color = alert_title(warning=True), 0xEED49F
    else:
        title, color = "Scrape update" if scrape else "Log update", 0xA6DA95
    context = _CONTEXT.validate_python(getattr(record, "context", {}))
    event = context.get("event")
    if scrape and event == "started":
        title, color = "Scrape started", 0xC6A0F6
    elif scrape and event == "completed" and record.levelno < logging.WARNING:
        title = "Scrape complete"
    elif scrape and event == "cancelled":
        title = "Scrape stopped"
    elif scrape and event == "timeout":
        title = "Scrape reached its time limit"
    message = record.getMessage()
    exception = record.exc_text
    if exception is None and record.exc_info:
        exception = logging.Formatter().formatException(record.exc_info)
    if record.levelno >= logging.WARNING or exception:
        summary = (
            safe_text(message)
            if event == "database_unavailable"
            else error_summary(exception or message)
        )
        context_message = (
            safe_text(message, 500) + "\n" if exception and "Traceback" not in message else ""
        )
        message = "```text\n" + context_message + summary + "\n```"
    fields: list[JsonValue] = [
        {"name": label, "value": _clip(str(context[key]), 120), "inline": True}
        for key, label in _FIELDS.items()
        if key in context and context[key] is not None
    ]
    return {
        "username": "Intern Radar Scraper" if scrape else "Intern Radar Logs",
        "allowed_mentions": {"parse": []},
        "embeds": [
            {
                "title": title,
                "description": _clip(message, 3600),
                "color": color,
                "fields": fields,
                "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
                "footer": {
                    "text": _clip(f"Intern Radar • {record.levelname} • {record.name}", 240)
                },
            }
        ],
    }
