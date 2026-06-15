import pytest

from job_backend.persistence.models import Document, DocumentKey, Filter, ReadQuery
from tests.test_postgres import PostgresTestDatabase
from tests.test_postgres import postgres as postgres


@pytest.mark.parametrize(
    ("predicate", "expected"),
    [
        (Filter("source", value="target"), {"match"}),
        (Filter("source", "ne", "target"), {"other", "missing", "null", "false"}),
        (Filter("source"), {"missing", "null"}),
        (Filter("source", value=False), {"false"}),
    ],
)
@pytest.mark.parametrize("source", [False, True])
def test_null_and_false_filters(
    postgres: PostgresTestDatabase, predicate: Filter, expected: set[str], source: bool
) -> None:
    values: dict[str, Document] = {
        "match": {"source": "target"},
        "other": {"source": "other"},
        "missing": {},
        "null": {"source": None},
        "false": {"source": False},
    }
    records: dict[DocumentKey, Document] = {
        ("jobs", key): {"id": key, **value} for key, value in values.items()
    }
    postgres.gateway.commit(dict.fromkeys(records), records)
    page = postgres.gateway.select(
        ReadQuery("jobs", predicate, fields=("id",), source=source), limit=10
    )
    assert {str(row["id"]) for row in page.items} == expected
    assert page.total == len(expected)
