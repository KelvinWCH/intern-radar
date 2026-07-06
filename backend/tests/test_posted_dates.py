import json

import pytest
from pydantic import JsonValue

from job_backend.persistence.database import Database
from job_backend.scrape.pipeline.heuristics.normalizer import HeuristicNormalizer
from job_backend.scrape.pipeline.models import RawDocument, ScrapeResult
from job_backend.scrape.pipeline.normalization import normalize_snapshot
from tests.helpers import ADAPTER, StubNormalizer, listing

POSTED = 1792108800


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"datePosted": "2026-10-16"}, POSTED),
        ({"publishedAt": POSTED * 1000}, POSTED),
        ({"updated_at": "2026-10-16", "created_at": POSTED}, None),
    ],
)
def test_structured_publication_fields(fields: dict[str, JsonValue], expected: int | None) -> None:
    document = RawDocument(
        content=json.dumps(
            {"company_name": "Example", "job": {"title": "Software Intern", **fields}}
        ),
        media_type="application/json",
        source_url="https://example.com/job",
    )
    assert HeuristicNormalizer().extract(document).jobs[0].date_posted == expected


def test_feed_date_wins(engine: Database) -> None:
    document = RawDocument(
        content=json.dumps(listing()),
        source_url="https://example.com/job",
        external_id="example-1",
        date_posted=POSTED,
    )
    normalizer = StubNormalizer()
    for _ in range(2):
        jobs = normalize_snapshot(engine, ADAPTER, ScrapeResult(1, [document]), normalizer)
        assert jobs[0].date_posted == POSTED
    assert normalizer.calls == 1
