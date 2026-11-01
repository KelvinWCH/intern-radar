import time
from datetime import date, datetime, timedelta
from typing import get_args
from zoneinfo import ZoneInfo

from job_backend.activity.models import ActivityDay, ActivityEvent, ActivitySummary, PipelineStage
from job_backend.jobs.models import ApplicationStatus
from job_backend.persistence.database import Database
from job_backend.persistence.models import Filter, Junction, Order, ReadQuery
from job_backend.persistence.session import Session

# days start at midnight in toronto
TIMEZONE = "America/Toronto"


def summarize_activity(
    engine: Database, *, days: int = 30, now: int | None = None
) -> ActivitySummary:
    if not 7 <= days <= 90:
        raise ValueError("Choose between 7 and 90 days")
    timestamp = int(time.time()) if now is None else now
    zone = ZoneInfo(TIMEZONE)
    today = datetime.fromtimestamp(timestamp, zone).date()
    start = today - timedelta(days=days - 1)
    daily = {
        start + timedelta(days=offset): ActivityDay(
            date=(start + timedelta(days=offset)).isoformat()
        )
        for offset in range(days)
    }
    with Session(engine, read_only=True) as session:
        total_applications = 0
        groups = session.groups(
            ReadQuery("activity_events", Filter("occurred_at", "le", timestamp), timezone=TIMEZONE),
            ("@event_day", "kind"),
        )
        for group in groups:
            day_text, kind, count = group["@event_day"], group["kind"], group["count"]
            if not isinstance(day_text, str) or not isinstance(count, int):
                raise ValueError("Invalid activity aggregate")
            if kind == "application_marked":
                total_applications += count
            bucket = daily.get(date.fromisoformat(day_text))
            if bucket is not None:
                bucket.actions += count
                bucket.applications += count if kind == "application_marked" else 0
                bucket.documents += count if kind == "documents_generated" else 0
                bucket.resume_updates += count if kind == "resume_updated" else 0
        counts: dict[str, int] = {}
        for row in session.groups(ReadQuery("job_user_data"), ("status",)):
            count = row["count"]
            counts[str(row["status"])] = count if isinstance(count, int) else 0
        midnight = int(datetime.combine(start, datetime.min.time(), tzinfo=zone).timestamp())
        recent = [
            ActivityEvent.model_validate(record)
            for record in session.select(
                ReadQuery(
                    "activity_events",
                    Junction(
                        (
                            Filter("occurred_at", "ge", midnight),
                            Filter("occurred_at", "le", timestamp),
                        )
                    ),
                    (
                        Order("occurred_at", descending=True, numeric=True),
                        Order("@key", descending=True),
                    ),
                    fields=("id", "kind", "occurred_at", "data"),
                    source=True,
                ),
                limit=20,
                count=False,
            ).items
        ]
    return ActivitySummary(
        start_date=start.isoformat(),
        end_date=today.isoformat(),
        generated_at=timestamp,
        total_applications=total_applications,
        active_days=sum(day.actions > 0 for day in daily.values()),
        days=list(daily.values()),
        pipeline=[
            PipelineStage(status=status, count=counts.get(status, 0))
            for status in get_args(ApplicationStatus)
            if status != "new"
        ],
        recent=recent,
    )
