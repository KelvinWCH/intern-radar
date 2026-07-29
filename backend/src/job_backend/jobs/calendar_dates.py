from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from job_backend.persistence.models import Interval


def posting_day(timestamp: int, zone: ZoneInfo) -> date:
    return datetime.fromtimestamp(timestamp, UTC if timestamp % 86400 == 0 else zone).date()


def posting_interval(start: date | None, before: date | None, zone: ZoneInfo) -> Interval | None:
    if start is None and before is None:
        return None

    def boundary(day: date, *, upper: bool) -> int:
        local = int(datetime.combine(day, time.min, zone).timestamp())
        utc = int(datetime.combine(day, time.min, UTC).timestamp())
        return max(local, utc) if upper else min(local, utc)

    return (
        "date_posted",
        boundary(start, upper=False) if start is not None else None,
        boundary(before, upper=True) if before is not None else None,
    )
