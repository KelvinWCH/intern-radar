from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo


def next_clock_time(hours: list[int], timezone: str, after: float, *, inclusive: bool) -> float:
    zone = ZoneInfo(timezone)
    date = datetime.fromtimestamp(after, zone).date()
    for offset in range(3):
        day = date + timedelta(days=offset)
        for hour in hours:
            local = datetime(day.year, day.month, day.day, hour, tzinfo=zone)
            utc = local.astimezone(UTC)
            if utc.astimezone(zone).replace(tzinfo=None) != local.replace(tzinfo=None):
                continue
            stamp = utc.timestamp()
            if stamp > after or (inclusive and stamp == after):
                return stamp
    raise ValueError("No scheduled local hour exists within the next three days")
