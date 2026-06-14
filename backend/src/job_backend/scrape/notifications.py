import re
from collections.abc import Sequence
from datetime import UTC, date, datetime, tzinfo
from urllib.parse import quote, urlsplit

from pydantic import JsonValue

from job_backend.common.discord import safe_text
from job_backend.common.logger import get_logger
from job_backend.jobs.company_priority import company_tier, job_priority
from job_backend.jobs.models import Job
from job_backend.persistence.database import Database
from job_backend.persistence.models import Filter, Junction, Order, ReadQuery
from job_backend.persistence.session import Session
from job_backend.scrape.models import JobReportItem

logger = get_logger(__name__)
_LEGEND = (
    "🔴 Tech · 🟡 Known employer · ⚪ Other\nToronto area first; tech → known → other in each area."
)


def markdown_text(value: str, limit: int) -> str:
    text = " ".join(safe_text(value, limit).split()).replace("@", "@\u200b")
    return re.sub(r"([\\*_~|\[\]()<>#])", r"\\\1", text)


def posted_day(timestamp: int, zone: tzinfo) -> date:
    return datetime.fromtimestamp(timestamp, UTC if timestamp % 86_400 == 0 else zone).date()


def safe_job_url(value: str | None) -> str | None:
    if not value or len(value) > 900 or safe_text(value, 1000) != value:
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
            return None
    except ValueError:
        return None
    encoded = quote(value, safe="/:?=&%+;,!$@.-_~")
    return encoded if len(encoded) <= 900 else None


def _entry(job: Job | JobReportItem) -> str:
    marker = {"tech": "🔴", "known": "🟡", None: "⚪"}[company_tier(job.company)]
    label = f"{markdown_text(job.company, 90)} — {markdown_text(job.title, 150)}"
    url = safe_job_url(job.application_url) or safe_job_url(job.apply_url)
    heading = f"[{label}](<{url}>)" if url else label
    details = [markdown_text(", ".join(job.locations) or "Location not listed", 180)]
    if job.terms:
        details.append(markdown_text(", ".join(job.terms), 100))
    if job.date_posted is not None:
        details.append(f"Posted <t:{job.date_posted}:d>")
    details.append(f"Found <t:{job.first_seen_at}:t>")
    return f"{marker} **{heading}**\n" + " · ".join(details)


def jobs_for_report(
    engine: Database, sources: set[str] | None, first_seen_from: int, first_seen_before: int
) -> list[JobReportItem]:
    with Session(engine, read_only=True) as session:
        filters: list[Filter | Junction] = [
            Filter("first_seen_at", "ge", first_seen_from),
            Filter("first_seen_at", "lt", first_seen_before),
            Filter("source_type", value="scraped"),
            Filter("deleted_at"),
            Filter("active", "ne", False),
            Filter("is_visible", "ne", False),
            Filter("is_canada_internship", value=True),
            Filter("is_toronto_area", "ne"),
        ]
        if sources is not None:
            filters.append(
                Junction(tuple(Filter("source", value=source) for source in sorted(sources)), "or")
            )
        query = ReadQuery(
            "jobs",
            Junction(tuple(filters)),
            (Order("@key"),),
            fields=tuple(JobReportItem.model_fields),
        )
        jobs: list[JobReportItem] = []
        position = 0
        while True:
            rows = session.select(query, limit=1000, offset=position, count=False).items
            jobs.extend(JobReportItem.model_validate(row) for row in rows)
            if len(rows) < 1000:
                break
            position += len(rows)
        jobs.sort(
            key=lambda job: (
                job_priority(job.company, job.is_toronto_area is True),
                -job.first_seen_at,
                job.id,
            )
        )
        return jobs


def scraped_job_embeds(
    engine: Database, sources: set[str], first_seen_from: int, first_seen_before: int
) -> list[dict[str, JsonValue]]:
    try:
        jobs = jobs_for_report(engine, sources, first_seen_from, first_seen_before)
    except Exception as error:
        logger.warning("Discord job list unavailable (%s)", type(error).__name__)
        return [
            {
                "title": "Scraped jobs",
                "description": "Job list unavailable. Open the daily report to retry.",
            }
        ]
    return job_report_embeds(jobs)


def job_report_embeds(
    jobs: Sequence[Job | JobReportItem], *, period: str = "this scrape"
) -> list[dict[str, JsonValue]]:
    entries = [_entry(job) for job in jobs]

    descriptions: list[str] = []
    current = _LEGEND
    for entry in entries:
        combined = current + "\n\n" + entry
        if len(combined.encode("utf-16-le")) // 2 > 3500:
            descriptions.append(current)
            current = _LEGEND + "\n\n" + entry
        else:
            current = combined
    if not entries:
        current += f"\n\nNo new open jobs from {period} match the daily report."
    descriptions.append(current)
    return [
        {
            "title": (
                f"Scraped jobs · {len(jobs)} new open listings · {index + 1}/{len(descriptions)}"
            ),
            "description": description,
            "color": 0xED8796,
            "footer": {"text": f"Daily report · All Canada · first discovered in {period}"},
        }
        for index, description in enumerate(descriptions)
    ]
