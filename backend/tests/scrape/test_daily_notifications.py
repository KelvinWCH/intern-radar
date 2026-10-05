import json
import re
from datetime import date

import httpx2
from pydantic import JsonValue, SecretStr, TypeAdapter

from job_backend.common.models import DailyJobsTarget
from job_backend.jobs.models import Job
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.scrape.daily_notifications import (
    DailyJobsPublisher,
    day_bounds,
)

WEBHOOK = SecretStr("https://discord.com/api/webhooks/123/daily-token")
TARGET = DailyJobsTarget(webhook_url=WEBHOOK)
DAY = date(2026, 10, 18)


def _save(engine: Database, company: str, *, day: date = DAY, source: str = "github") -> Job:
    start, _end = day_bounds(day, "America/New_York")
    with Session(engine) as session, session.begin():
        job = Job(
            source=source,
            external_id=company,
            company=company,
            title="Software Intern",
            locations=["Toronto, ON"],
            first_seen_at=start + 3600,
            is_canada_internship=True,
            is_toronto_area=True,
            application_url="https://example.com/jobs/" + company.replace(" ", "-"),
        )
        session.add(job)
        return job


def _payload(request: httpx2.Request) -> dict[str, object]:
    matched = re.search(rb'name="payload_json"\r\n\r\n(.*?)\r\n--', request.content, re.S)
    assert matched is not None
    return json.loads(matched.group(1))


def _texts(value: object) -> str:
    found: list[str] = []

    def walk(item: JsonValue) -> None:
        if isinstance(item, list):
            for child in item:
                walk(child)
        elif isinstance(item, dict):
            if item.get("type") == 10:
                found.append(str(item.get("content")))
            walk(item.get("components"))

    walk(TypeAdapter(JsonValue).validate_python(value))
    return "\n".join(found)


def _html(request: httpx2.Request) -> str:
    matched = re.search(
        rb"Content-Type: text/html; charset=utf-8\r\n\r\n(.*?)\r\n--", request.content, re.S
    )
    assert matched is not None
    return matched.group(1).decode()


def test_one_message_per_day(engine: Database) -> None:
    requests: list[httpx2.Request] = []

    def deliver(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"id": str(100 + len(requests))})

    transport = httpx2.MockTransport(deliver)
    _save(engine, "Google")
    DailyJobsPublisher(TARGET, engine.local_path, transport=transport).publish(engine, DAY)
    _save(engine, "TD Bank", source="company-board")
    restarted = DailyJobsPublisher(TARGET, engine.local_path, transport=transport)
    restarted.publish(engine, DAY)
    restarted.publish(engine, DAY)
    tomorrow = date(2026, 10, 19)
    _save(engine, "Tomorrow employer", day=tomorrow, source="search")
    restarted.publish(engine, tomorrow)
    assert [request.method for request in requests] == ["POST", "PATCH", "PATCH", "POST"]
    assert all(request.url.path.endswith("/messages/101") for request in requests[1:3])
    assert "Google" in _html(requests[1]) and "TD Bank" in _html(requests[1])
    assert _html(requests[1]).index("Google") < _html(requests[1]).index("TD Bank")
    assert "Tomorrow employer" not in _html(requests[1])
    assert "Google" not in _html(requests[3])
    assert "**2 new listings**" in _texts(_payload(requests[2])["components"])
    assert all(_payload(request)["allowed_mentions"] == {"parse": []} for request in requests)
    assert all(request.url.params["with_components"] == "true" for request in requests)
    assert _payload(requests[1])["attachments"] == [
        {"id": 0, "filename": "daily-jobs-2026-10-18.html"}
    ]
    assert "daily-token" not in "".join(
        path.read_text() for path in restarted.directory.glob("*.json")
    )
