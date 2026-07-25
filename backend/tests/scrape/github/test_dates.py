from datetime import UTC, datetime

import pytest

from job_backend.scrape.github.utils.dates import parse_posted_date

NOW = int(datetime(2026, 10, 17, 12, tzinfo=UTC).timestamp())


@pytest.mark.parametrize("value", ["2026-10-16", "Oct 16, 2026", "Oct 16"])
def test_relative_dates(value: str) -> None:
    expected = int(datetime(2026, 10, 16, tzinfo=UTC).timestamp())
    assert parse_posted_date(value, now=NOW) == expected


@pytest.mark.parametrize("value", [None, "First seen Oct 17, 2026", "2026-02-30"])
def test_missing_dates_unknown(value: object) -> None:
    assert parse_posted_date(value, now=NOW) is None
