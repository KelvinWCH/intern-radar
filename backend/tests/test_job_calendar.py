from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from job_backend.jobs.calendar_dates import posting_interval


def test_daylight_saving_interval() -> None:
    interval = posting_interval(date(2026, 11, 1), date(2026, 11, 2), ZoneInfo("America/New_York"))
    assert interval == (
        "date_posted",
        int(datetime(2026, 11, 1, tzinfo=UTC).timestamp()),
        int(datetime(2026, 11, 2, 5, tzinfo=UTC).timestamp()),
    )
